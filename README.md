# VTU Diary Automation (n8n + Python Logic)

This project automates the process of filling and submitting VTU internship diary entries by integrating:

- ISPARK curriculum API (to fetch lesson content)
- Gemini AI (to generate structured diary entries)
- VTU API (to submit diary entries)
- n8n (to orchestrate the entire workflow)

---

## 🚀 Overview

Instead of manually writing daily diary entries, this system:

1. Takes input (phase, week, day, lesson, date)
2. Fetches lesson content from ISPARK
3. Generates a structured diary using Gemini AI
4. Extracts relevant skills
5. Submits the entry directly to VTU portal

---

## 🧠 Architecture
