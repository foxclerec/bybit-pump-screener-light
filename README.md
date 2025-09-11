pip install -r requirements.txt
pip freeze > requirements.txt
===========================================

# Проверка звука
python -m app.screener.tools.sound_diag

# Проверка сети и биржи
python app/screener/tools/net_test.py
python app/screener/tools/net_test.py --cycles 3 --interval 10 --symbol BTCUSDT --with-kline
===========================================


0. NEW DB
flask --app app:create_app init-db

1. ACTIVATE
source .venv/Scripts/activate

2. SCREENER 
flask --app app:create_app screener-run

3. WEB
flask --app app:create_app run
===============================================

python -m app.screener.tools.levels_test