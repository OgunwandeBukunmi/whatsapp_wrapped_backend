from fastapi import FastAPI, UploadFile, File
import re
import pandas as pd
from collections import Counter
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://whatsappwrapped-omega.vercel.app"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def defaultData():
    with open("chat.txt", "r", encoding="utf-8") as f:
        text = f.read()
    return text

def to_dataframe(messages):
    df = pd.DataFrame(messages)

    df["datetime"] = pd.to_datetime(
        df["date"] + " " + df["time"],
        format="%d/%m/%Y %H:%M:%S"
    )

    df["date_only"] = df["datetime"].dt.date

    return df

def clean_text(text):
    return text.replace("\u200e", "").replace("\r", "")

def parse_chat(text):
    pattern = r"\[(\d{2}/\d{2}/\d{4}), (\d{2}:\d{2}:\d{2})\] (.*?): (.*)"
    
    messages = []
    current_message = None

    for line in text.split("\n"):
        match = re.match(pattern, line)

        ignored_keywords = [
            "image omitted",
            "audio omitted",
            "video omitted",
            "sticker omitted",
            "Messages and calls are end-to-end encrypted",
            "<Media omitted>"
        ]

        # inside your parser, after extracting message:


        if match:
            date, time, sender, message = match.groups()

            current_message = {
                "date": date,
                "time": time,
                "sender": sender,
                "message": message
            }
            if any(keyword in current_message["message"] for keyword in ignored_keywords):
                continue 
            messages.append(current_message)

        else:
            # Handle multi-line messages (VERY IMPORTANT)
            if current_message:
                current_message["message"] += " " + line.strip()

    return messages


def get_names(df):
    return df["sender"].dropna().unique().tolist()

def message_stats_per_day(df):
    counts = df.groupby("date_only").size()

    return {
        "longest_day": str(counts.idxmax()),
        "longest_count": int(counts.max()),
        "shortest_day": str(counts.idxmin()),
        "shortest_count": int(counts.min())
    }

def word_stats(df):
    text = " ".join(df["message"]).lower()

    words = re.findall(r"\b\w+\b", text)
    
    # stopwords = {"the", "is", "and", "i", "that" , "you" , "to" , "it" , "and" , "t" , "s" , "a" , "an" , "that" , "like" , "me", "not" , "what" , "we" , ""
    # }

    # words = [w for w in words if w not in stopwords]
    counter = Counter(words)

    most_common = counter.most_common(20)
    least_common = counter.most_common()[-20:]

    return {
        "most_common": most_common,
        "least_common": least_common
    }

def longest_silence(df):
    df = df.sort_values("datetime").reset_index(drop=True)

    # Calculate time differences
    df["gap"] = df["datetime"].diff()

    # Find index of the largest gap
    max_gap_index = df["gap"].idxmax()

    # Get the two timestamps
    end_time = df.loc[max_gap_index, "datetime"]
    start_time = df.loc[max_gap_index - 1, "datetime"]

    max_gap = df.loc[max_gap_index, "gap"]

    return {
        "start_of_silence": str(start_time),
        "end_of_silence": str(end_time),
        "duration": str(max_gap)
    }

def average_messages(df):
    daily_counts = df.groupby("date_only").size()
    return float(daily_counts.mean())


def longest_streak(df):
    days = sorted(df["date_only"].unique())

    streak = 1
    max_streak = 1

    for i in range(1, len(days)):
        if (days[i] - days[i-1]).days == 1:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 1

    return max_streak

def conversation_starter(df):
    first_messages = (
        df.sort_values("datetime")
          .groupby("date_only")
          .first()
    )

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
    text = content.decode("utf-8")
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
    }
    print("Response Sent")
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
    }
    print("Response Sent" , result)
    return result

@app.get("/health")
async def health():
    return {"status": "ok"}
