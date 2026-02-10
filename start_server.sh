#!/bin/bash
cd /home/jeff/Farmart/Farmart_backend
export FLASK_APP=app.py
export FLASK_ENV=development
source .env
python app.py
