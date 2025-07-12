from flask import Flask, render_template

app = Flask(__name__)

@app.route('/')
def home():
    return render_template('dashboard.html',
                           username="Anmol Gupta",
                           email="anmol@example.com",
                           join_date="July 2024")

if __name__ == '__main__':
    app.run(debug=True)
