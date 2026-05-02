from fastapi import FastAPI, UploadFile, File
import re
import pandas as pd
from collections import Counter
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "https://whatsappwrapped-omega.vercel.app" , "https://whatsappwrapped.pxxl.click" , "http://localhost:3003"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def defaultData():
    with open("chat.txt", "r", encoding="utf-8") as f:
        text = f.read()
    return text
    
def format_duration(td):
    total_seconds = int(td.total_seconds())

    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60

    return f"{days}d {hours}h {minutes}m {seconds}s"

def peak_hours(df):
    df["hour"] = df["datetime"].dt.hour
    return int(df["hour"].value_counts().idxmax())

def message_share(df):
    counts = df["sender"].value_counts()
    total = counts.sum()

    return {k: round(v / total * 100, 1) for k, v in counts.items()}

def ghosting(df, threshold_hours=24):
    if df.empty or "datetime" not in df:
        return 0

    # Drop rows with no datetime → ensures valid gaps
    df = df.dropna(subset=["datetime"]).sort_values("datetime").reset_index(drop=True)

    if len(df) < 2:
        return 0

    # Calculate time gaps between consecutive messages
    df["gap"] = df["datetime"].diff()
    gaps = df["gap"]

    # ghost_events is now a DataFrame containing only rows where gap > threshold
    ghost_events = gaps[gaps > pd.Timedelta(hours=threshold_hours)]

    return len(ghost_events)

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
        "messages and calls are end-to-end encrypted",
        "<Media omitted>",
        "media omitted",
        "Media omitted",
        "message omitted",
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
       "u", "dey","it", "s","media", "omitted", "t","to", "a", "the", "and", "but", "or", "for", "nor", "so", "yet", "with", "on", "in", "at", "by", "to", "from", "about", "as", "into", "like", "through", "after", "over", "between", "out", "against", "during", "without"
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

    df = df.dropna(subset=["datetime"]).sort_values("datetime").reset_index(drop=True)

    if len(df) < 1:
        return None

    # 🔹 Calculate past gaps
    df["gap"] = df["datetime"].diff()
    gaps = df["gap"].dropna()

    longest_past = None

    if not gaps.empty:
        max_gap_index = gaps.idxmax()
        pos = max_gap_index

        longest_past = {
            "start": df.iloc[pos - 1]["datetime"],
            "end": df.iloc[pos]["datetime"],
            "duration": df.iloc[pos]["gap"],
            "type": "past"
        }

    # 🔹 Calculate ongoing silence
    now = pd.Timestamp.now()
    last_time = df.iloc[-1]["datetime"]
    current_gap = now - last_time

    current_silence = {
        "start": last_time,
        "end": now,
        "duration": current_gap,
        "type": "ongoing"
    }

    # 🔥 Compare both
    if longest_past is None or current_gap > longest_past["duration"]:
        result = current_silence
        result["is_current"] = True
    else:
        result = longest_past
        result["is_current"] = False

    # Optional: convert to string for API response



    duration_td = result["duration"]  # keep as timedelta

    result["duration"] = format_duration(duration_td)
    result["start"] = result["start"].strftime("%Y-%m-%d %H:%M:%S")
    result["end"] = result["end"].strftime("%Y-%m-%d %H:%M:%S")

    
    return result
def average_messages(df):
    if df.empty or "date_only" not in df:
        return 0.0

    daily_counts = df.dropna(subset=["date_only"]).groupby("date_only").size()

    if daily_counts.empty:
        return 0.0

    return float(daily_counts.mean())


def longest_streak(df):
    if df.empty or "date_only" not in df:
        return {"count": 0, "is_current": False, "start": None, "end": None}

    days = sorted(df["date_only"].dropna().unique())

    if len(days) == 0:
        return {"count": 0, "is_current": False, "start": None, "end": None}

    from datetime import date, timedelta

    streak = 1
    max_streak = 1
    max_streak_end = days[0]

    for i in range(1, len(days)):
        if (days[i] - days[i - 1]).days == 1:
            streak += 1
            if streak > max_streak:
                max_streak = streak
                max_streak_end = days[i]
        else:
            streak = 1

    today = date.today()
    # Convert max_streak_end to date if it's a Timestamp
    end_date = max_streak_end.date() if hasattr(max_streak_end, 'date') else max_streak_end
    start_date = end_date - timedelta(days=max_streak - 1)
    is_current = (today - end_date).days <= 1

    return {
        "count": max_streak,
        "is_current": is_current,
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
    }
    
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

    streak_result = longest_streak(df)
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
        "first_message": firstmessage(df),
        "ghosting_count": ghosting(df),
        "peak_hours": peak_hours(df),
        "message_share": message_share(df)
    }

    balance_score = 0
    silence_penalty = 0
    effort_score = 0
    activity_score = 0
    consistency_score = 0

    activity_score = min(result["average_messages_per_day"] * 2, 100)
    consistency_score = min(result["longest_streak"]["count"] * 2, 100)
    
    starters = list(result["conversation_starters"].values())

    if len(starters) == 2:
        diff = abs(starters[0] - starters[1])
        total = sum(starters)
        balance_score = 100 - (diff / total * 100)
    else:
        balance_score = 50


    if not result["longest_silence"]:
        silence_penalty = 0
    else:
        td = pd.to_timedelta(result["longest_silence"]["duration"])
        days = td.total_seconds() / 86400

        silence_penalty =min(days * 2, 25)

    effort_score = min(result["total_length"] / 10, 50)

    final_score = (
        activity_score * 0.25 +
        consistency_score * 0.20 +
        balance_score * 0.25 +
        effort_score * 0.30
    ) - silence_penalty 
    final_score = max(0, min(100, round(final_score)))

    result["activity_score"] = activity_score
    result["balance_score"] = balance_score
    result["consistency_score"] = consistency_score
    result["silence_penalty"] = silence_penalty
    result["effort_score"] = effort_score
    result["final_score"] = final_score

    if final_score >= 75:
        relationship_status = "Just Marry at this point🔥"
    elif final_score >= 65 and final_score <=74:
        relationship_status = "Ride or die"
    elif final_score >= 55 and final_score <=65:
        relationship_status = "Fucking Good friends"
    elif final_score >= 40 and final_score <=54:
        relationship_status = "Better Friends"
    elif  final_score >= 30 and final_score <=39:
        relationship_status = "Literally just friends😑"
    else:
        relationship_status = "ewww"
    
    result["relationship_status"] = relationship_status


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
        "total_length": total_length,
        "first_message": firstmessage(df)
    }

    balance_score = 0
    silence_penalty = 0
    effort_score = 0
    activity_score = 0
    consistency_score = 0
    relationship_status = ""

    activity_score = min(result["average_messages_per_day"] * 2, 100)
    consistency_score = min(result["longest_streak"]["count"] * 2, 100)
    
    starters = list(result["conversation_starters"].values())

    if len(starters) == 2:
        diff = abs(starters[0] - starters[1])
        total = sum(starters)
        balance_score = 100 - (diff / total * 100)
    else:
        balance_score = 50


    if not result["longest_silence"]:
        silence_penalty = 0
    else:
        td = pd.to_timedelta(result["longest_silence"]["duration"])
        days = td.total_seconds() / 86400

        silence_penalty = min(days * 2, 25)

    effort_score = min(result["total_length"] / 20, 50)

    final_score = (
        activity_score * 0.25 +
        consistency_score * 0.20 +
        balance_score * 0.25 +
        effort_score * 0.20
    ) - silence_penalty 

    result["activity_score"] = activity_score
    result["balance_score"] = balance_score
    result["consistency_score"] = consistency_score
    result["silence_penalty"] = silence_penalty
    result["effort_score"] = effort_score
    result["final_score"] = final_score

    if final_score >= 75:
        relationship_status = "Just Marry at this point🔥"
    elif final_score >= 65 and final_score <=74:
        relationship_status = "Ride or die"
    elif final_score >= 55 and final_score <=64:
        relationship_status = "Fucking Good friends"
    elif final_score >= 40 and final_score <=54:
        relationship_status = "Better Friends"
    elif  final_score >= 30 and final_score <=39:
        relationship_status = "Literally just friends😑"
    else:
        relationship_status = "ewww"
    
    result["relationship_status"] = relationship_status

    print("Response Sent" , result)
    return result

@app.get("/health")
def health():
    return {"status": "ok"}
