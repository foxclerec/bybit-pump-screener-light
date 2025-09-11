# app/screener/tools/play_test.py
from app.screener.utils.alert import set_sound_files, play_alert

if __name__ == "__main__":
    set_sound_files({"pulse": "pulse.mp3", "boom": "boom.mp3"})
    play_alert("pulse")
    play_alert("boom")
    print("Dispatched pulse & boom sounds.")
