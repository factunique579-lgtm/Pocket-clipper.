# Pocket-clipper.
# Pocket Clipper 📱✂️

A 100% free, offline-capable YouTube AI Clipper that runs entirely on your Android phone via **Termux**.

## Features
- **Zero Cost:** No OpenAI, OpusClip, or cloud GPU fees.
- **On-Device AI:** Uses `whisper.cpp` for local speech-to-text transcription.
- **Auto Vertical Crop:** Converts 16:9 YouTube videos into 9:16 Shorts/Reels.
- **Burned-In Captions:** Automatically overlays subtitles onto every clip.

## Prerequisites
1. Install **Termux** from [F-Droid](https://f-droid.org/packages/com.termux/) (do **not** use the Google Play Store version, as it is outdated).
2. At least **2 GB of free storage** and **4 GB+ RAM** recommended.

## Installation
Open Termux and run:

```bash
pkg update && pkg upgrade -y
pkg install git -y
git clone [https://github.com/YOUR_USERNAME/pocket-clipper.git](https://github.com/YOUR_USERNAME/pocket-clipper.git)
cd pocket-clipper
chmod +x setup.sh
./setup.sh
