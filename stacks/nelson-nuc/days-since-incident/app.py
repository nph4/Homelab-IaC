from flask import Flask, render_template, redirect
from datetime import date
import os

app = Flask(__name__)
DATA_FILE = "/data/last_reset.txt"


def get_last_reset():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            return date.fromisoformat(f.read().strip())
    today = date.today()
    save_reset(today)
    return today


def save_reset(d):
    os.makedirs("/data", exist_ok=True)
    with open(DATA_FILE, "w") as f:
        f.write(d.isoformat())


@app.route("/")
def index():
    last_reset = get_last_reset()
    days = (date.today() - last_reset).days
    return render_template("index.html", days=days, last_reset=last_reset.strftime("%B %d, %Y"))


@app.route("/reset", methods=["POST"])
def reset():
    save_reset(date.today())
    return redirect("/")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
