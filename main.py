from fastapi import FastAPI, UploadFile, File
import re
import pandas as pd
from collections import Counter
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "https://whatsappwrapped-omega.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def defaultData():
    with open("chat.txt", "r", encoding="utf-8") as f:
        text = f.read()
    return text

def firstmessage(df):
    if df.empty or "datetime" not in df or df["datetime"].dropna().empty:
        return None
    return str(df.dropna(subset=["datetime"]).iloc[0]["datetime"])

def to_dataframe(messages):
    df = pd.DataFrame(messages)
    if df.empty:
        df["datetime"] = pd.NaT
        df["date_only"] = None
        return df

    raw = df["date"] + " " + df["time"]

    datetime_formats = [
        "%d/%m/%Y %H:%M:%S",   # 31/12/2024 14:05:30
        "%d/%m/%Y %H:%M",      # 31/12/2024 14:05
        "%m/%d/%Y %H:%M:%S",   # 12/31/2024 14:05:30
        "%m/%d/%Y %H:%M",      # 12/31/2024 14:05
        "%d/%m/%Y %I:%M %p",   # 31/12/2024 2:05 pm
        "%d/%m/%Y %I:%M:%S %p",# 31/12/2024 2:05:30 pm
        "%m/%d/%y %H:%M",      # 12/31/24 14:05
        "%d/%m/%y %H:%M",      # 31/12/24 14:05
    ]

    parsed = pd.Series([pd.NaT] * len(raw), index=raw.index)

    for fmt in datetime_formats:
        mask = parsed.isna()
        if not mask.any():
            break
        parsed[mask] = pd.to_datetime(raw[mask], format=fmt, errors="coerce")

    # Fallback: let pandas infer anything still unparsed
    remaining = parsed.isna()
    if remaining.any():
        parsed[remaining] = pd.to_datetime(raw[remaining], dayfirst=True, errors="coerce")

    df["datetime"] = parsed
    print(df["datetime"])

    df["date_only"] = df["datetime"].dt.date

    return df
def clean_text(text):
    return text.replace("\u200e", "").replace("\r", "")

def parse_chat(text):
    patterns = [
    r"(\d{1,2}/\d{1,2}/\d{4}),\s*(\d{1,2}:\d{2})\s?(?:AM|PM|am|pm)\s*-\s*(.*?):\s*(.*)",
    r"\[(\d{1,2}/\d{1,2}/\d{2,4}),\s*(\d{1,2}:\d{2}:\d{2})\s?(?:AM|PM|am|pm)\]\s*(.*?):\s*(.*)",
    r"(\d{1,2}/\d{1,2}/\d{2}),\s*(\d{1,2}:\d{2})\s?(?:AM|PM|am|pm)\s*-\s*(.*?):\s*(.*)",
    r"(\d{1,2}/\d{1,2}/\d{2,4}),\s*(\d{1,2}:\d{2})(?:\s?(?:AM|PM|am|pm))?\s*-\s*(.*?):\s*(.*)",
    r"\[(\d{2}/\d{2}/\d{4}), (\d{2}:\d{2}:\d{2})\] (.*?): (.*)",
    r"(\d{1,2}/\d{1,2}/\d{4}),\s*(\d{1,2}:\d{2})\s*-\s*(.*?):\s*(.*)",
    r"(\d{1,2}/\d{1,2}/\d{2}),\s*(\d{2}:\d{2})\s*-\s*(.*?):\s*(.*)",
    r"\[(\d{2}/\d{2}/\d{4}), (\d{2}:\d{2}:\d{2})\] (.*?): (.*)",  # [date, time]
    r"(\d{1,2}/\d{1,2}/\d{4}), (\d{1,2}:\d{2}) - (.*?): (.*)",
    r"(\d{1,2}/\d{1,2}/\d{4}), (\d{1,2}:\d{2})\s?[ap]m - (.*?): (.*)",
    r"(\d{1,2}/\d{1,2}/\d{2}),\s*(\d{1,2}:\d{2})\s?[APMapm]{2}\s*-\s*(.*?):\s*(.*)" ,
    r"(\d{1,2}/\d{1,2}/\d{2}),\s*(\d{1,2}:\d{2})\s*-\s*(.*)" 
    r"(\d{1,2}/\d{1,2}/\d{2}),\s*(\d{2}:\d{2})\s*-\s*(.*?):\s*(.*)"  # date, time -
    ]

   
    messages = []
    current_message = None

    ignored_keywords = [
        "image omitted",
        "audio omitted",
        "video omitted",
        "sticker omitted",
        "Messages and calls are end-to-end encrypted",
        "<Media omitted>"
        "message omitted"
        "edited"
    ]



    for line in text.split("\n"):
        line = line.strip()

        # 🔥 Normalize weird unicode spaces (VERY IMPORTANT)
        line = line.replace("\u202f", " ")  # fixes "11:06 pm"

        match = None

        for p in patterns:
            match = re.match(p, line, re.IGNORECASE)
            if match:
                break

        if match:
            date, time, sender, message = match.groups()

            current_message = {
                "date": date,
                "time": time,
                "sender": sender,
                "message": message
            }

            if any(keyword.lower() in message.lower() for keyword in ignored_keywords):
                current_message = None
                continue

            messages.append(current_message)

        else:
            if current_message:
                current_message["message"] += " " + line

    if not messages:
        raise ValueError("No messages parsed — format mismatch")

    return messages

def get_names(df):
    return df["sender"].dropna().unique().tolist()

def message_stats_per_day(df):
    if df.empty or "datetime" not in df.columns:
        return {
            "longest_day": None,
            "max_messages": 0,
            "daily_counts": {}
        }

    df = df.dropna(subset=["datetime"])

    if df.empty:
        return {
            "longest_day": None,
            "max_messages": 0,
            "daily_counts": {}
        }

    counts = df.groupby(df["datetime"].dt.date).size()

    if counts.empty:
        return {
            "longest_day": None,
            "max_messages": 0,
            "daily_counts": {}
        }

    return {
        "longest_day": str(counts.idxmax()),
        "shortest_day": str(counts.idxmin()),
        "max_messages": int(counts.max()),
        "min_messages": int(counts.min()),
        "daily_counts": counts.to_dict()
    }

def word_stats(df):
    words_to_ignore = [
        "t","to", "a", "the", "and", "but", "or", "for", "nor", "so", "yet", "with", "on", "in", "at", "by", "to", "from", "about", "as", "into", "like", "through", "after", "over", "between", "out", "against", "during", "without"
    ]
    
    if df.empty or "message" not in df:
        return {"most_common": [], "least_common": []}

    text = " ".join(df["message"].dropna()).lower()

    words = re.findall(r"\b\w+\b", text)
    


    if not words:
        return {"most_common": [], "least_common": []}

    words = [w for w in words if w not in words_to_ignore]

    counter = Counter(words)

    most_common = counter.most_common(20)
    least_common = counter.most_common()[-20:]

    return {
        "most_common": most_common,
        "least_common": least_common
    }
def longest_silence(df):
    if df.empty or "datetime" not in df:
        return None

    df = df.dropna(subset=["datetime"]).sort_values("datetime")

    if len(df) < 2:
        return None

    df["gap"] = df["datetime"].diff()

    gaps = df["gap"].dropna()

    if gaps.empty:
        return None

    max_gap_index = gaps.idxmax()
    pos = df.index.get_loc(max_gap_index)

    if pos == 0:
        return None

    return {
        "start": str(df.iloc[pos - 1]["datetime"]),
        "end": str(df.iloc[pos]["datetime"]),
        "duration": str(df.iloc[pos]["gap"])
    }
def average_messages(df):
    if df.empty or "date_only" not in df:
        return 0.0

    daily_counts = df.dropna(subset=["date_only"]).groupby("date_only").size()

    if daily_counts.empty:
        return 0.0

    return float(daily_counts.mean())


def longest_streak(df):
    if df.empty or "date_only" not in df:
        return 0

    days = sorted(df["date_only"].dropna().unique())

    if len(days) == 0:
        return 0

    streak = 1
    max_streak = 1

    for i in range(1, len(days)):
        if (days[i] - days[i - 1]).days == 1:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 1

    return max_streak
    
def conversation_starter(df):
    if df.empty or "datetime" not in df:
        return {}

    df = df.dropna(subset=["datetime"])

    if df.empty:
        return {}

    first_messages = (
        df.sort_values("datetime")
          .groupby("date_only")
          .first()
    )

    if "sender" not in first_messages:
        return {}

    return first_messages["sender"].value_counts().to_dict()
# @app.post("/upload")
# async def upload_chat(file: UploadFile = File(...)):
#     content = await file.read()
#     text = content.decode("utf-8")
#     messages = parse_chat(text)
#     df = to_dataframe(messages)
#     return {"length": len(text)}

def try_something(df):

    print(df.head())

@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    content = await file.read()
    text = clean_text(content.decode("utf-8"))
    messages = parse_chat(text)
    df = to_dataframe(messages)
    print(df)
    if df.empty:
        return {
            "error": "No valid messages parsed from chat",
            "users": [],
            "total_length": 0
        }

    total_length = df.dropna().shape[0]
    result = {
        "users": get_names(df),
        "message_stats": message_stats_per_day(df),
        "word_stats": word_stats(df),
        "longest_silence": longest_silence(df),
        "average_messages_per_day": average_messages(df),
        "longest_streak": longest_streak(df),
        "conversation_starters": conversation_starter(df),
        "total_length": total_length,
        "first_message": firstmessage(df)
    }

    return result


@app.get("/default")
async def analyze():
    text = defaultData()
    text = clean_text(text)
    messages = parse_chat(text)
    df = to_dataframe(messages)
    total_length = df.dropna().shape[0]

    result = {
        "users": get_names(df),
        "message_stats": message_stats_per_day(df),
        "word_stats": word_stats(df),
        "longest_silence": longest_silence(df),
        "average_messages_per_day": average_messages(df),
        "longest_streak": longest_streak(df),
        "conversation_starters": conversation_starter(df),
        "total_length" : total_length,
        "first_message" : firstmessage(df)
    }
    print("Response Sent" , result)
    return result

@app.get("/health")
async def health():
    return {"status": "ok"}
