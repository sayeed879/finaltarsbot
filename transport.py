import pandas as pd
import re

# File paths
input_file = r"C:\TARSBOTSQL\my_telegram_bot\Drive_PhhDF_Links.csv"
output_file = r"C:\TARSBOTSQL\my_telegram_bot\pdf.csv"

# Read CSV
df = pd.read_csv(input_file, dtype=str)
df.columns = [c.lower().strip() for c in df.columns]

# Detect possible columns
title_col = next((c for c in df.columns if "title" in c or "name" in c), None)
link_col = next((c for c in df.columns if "link" in c), None)

titles, links, classes, frees, keywords = [], [], [], [], []

for _, row in df.iterrows():
    title = str(row.get(title_col, "")).strip()
    link = str(row.get(link_col, "")).strip()

    # ✅ Keep full title
    short_title = title

    # ✅ In search_keywords, take only what’s before hyphen
    if "-" in title:
        kw = title.split("-", 1)[0].strip()
    else:
        kw = title.strip()

    # ✅ Class detection
    t_lower = title.lower()
    if re.search(r"\b11\b|xi", t_lower):
        cls = "11"
    elif re.search(r"\b12\b|xii", t_lower):
        cls = "12"
    else:
        cls = ""

    # ✅ Always "no" for is_free
    titles.append(short_title)
    links.append(link)
    classes.append(cls)
    frees.append("no")
    keywords.append(kw)

# ✅ Create final CSV
new_df = pd.DataFrame({
    "title": titles,
    "drive_link": links,
    "class_tag": classes,
    "is_free": frees,
    "search_keywords": keywords
})

new_df.to_csv(output_file, index=False)
print("✅ Done! Saved as:", output_file)
