from flask import Flask, render_template, request, jsonify
from flask_caching import Cache
import json
import requests
from config import api_key
import datetime as dt
import pandas as pd
import numpy as np
from tensorflow.keras.models import load_model
# from boto.s3.connection import S3Connection



config = {
    "DEBUG": True,          # some Flask specific configs
    "CACHE_TYPE": "simple", # Flask-Caching related configs
    "CACHE_DEFAULT_TIMEOUT": 300
}

app = Flask(__name__)

# tell Flask to use the above defined config
app.config.from_mapping(config)
cache = Cache(app)

# Create and index route
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/weather_viz')
def weather():
    return render_template('weather_viz.html')

# Route to create lstm forecast
@app.route("/model_data")
@cache.cached(timeout=1800)
def apply_model():
    days = pd.date_range(dt.datetime.utcnow().date() - dt.timedelta(days=6), periods=6, freq="D").tolist()
    request_data = []
    for day in days:
        request_data.append(
            requests.get(
                f"http://api.openweathermap.org/data/2.5/onecall/timemachine?lat=29.7604&lon=-95.3698&dt={int(day.timestamp())}&units=imperial&appid={api_key}"
            ).json()
        )
    
    weather_data = {}
    i=0
    for day in request_data:
        weather_day = {
            "temp": np.nanmean(np.array([hour["temp"] if "temp" in hour else np.NaN for hour in day["hourly"]])),
            "dewp": np.nanmax(np.array([hour["dew_point"] if "dew_point" in hour else np.NaN for hour in day["hourly"]])),
            "slp": np.nanmean(np.array([hour["pressure"] if "pressure" in hour else np.NaN for hour in day["hourly"]] )),
            "visib": np.nanmean(np.array([hour["visibility"] if "visibility" in hour else np.NaN for hour in day["hourly"]])),
            "wdsp": np.nanmean(np.array([hour["wind_speed"] if "wind_speed" in hour else np.NaN for hour in day["hourly"]])),
            
            "max": np.max(np.array([hour["temp"] if "temp" in hour else np.NaN for hour in day["hourly"]])),
            "min": np.min(np.array([hour["temp"] if "temp" in hour else np.NaN for hour in day["hourly"]])),
            "fog": np.nanmean(np.array([1 if hour["weather"][0]["main"] == "Fog" else 0 for hour in day["hourly"]] )),
            "rain_drizzle": np.nanmean(np.array([1 if hour["weather"][0]["main"] in ["Rain", "Drizzle"] else 0 for hour in day["hourly"]])),
            "snow_ice_pellets": np.nanmean(np.array([1 if hour["weather"][0]["main"] == "Snow" else 0 for hour in day["hourly"]] )),
            "hail": np.nanmean(np.array([1 if hour["weather"][0]["main"] == "Hail" else 0 for hour in day["hourly"]])),
            "thunder": np.nanmean(np.array([1 if hour["weather"][0]["main"] == "Thunderstorm" else 0 for hour in day["hourly"]]))
        }
        weather_data[days[i].date()] = weather_day
        i += 1

    lookup_year = pd.read_csv("Assets/last_year_lookup.csv", index_col="Date", parse_dates=["Date"])

    differenced_df = pd.DataFrame(weather_data).transpose().sub(
        lookup_year[pd.Timestamp(dt.date.today() - dt.timedelta(days=371)):pd.Timestamp(dt.date.today() - dt.timedelta(days=366))].values
    )

    scalers = pd.read_csv("Assets/scaler_data.csv")
    differenced_df = differenced_df.sub(np.array(scalers["scale_means"]))
    differenced_df = differenced_df.div(np.array(np.sqrt(scalers["scale_vars"])))
    
    model = load_model("loss_42")
    predictions = model.predict(np.expand_dims(differenced_df, axis=0))
    predictions = predictions * np.array(np.sqrt(scalers["scale_vars"]))
    predictions += lookup_year[pd.Timestamp(dt.date.today() - dt.timedelta(days=366)):pd.Timestamp(dt.date.today() - dt.timedelta(days=361))].values
    
    return pd.DataFrame(predictions[0], columns=differenced_df.columns, index=pd.date_range(dt.datetime.utcnow().date(), periods=6, freq="D")).to_json(orient="index")

@app.route("/forecast_data")
@cache.cached(timeout=1800)
def get_forecast():
    weather_response = requests.get(f'https://api.openweathermap.org/data/2.5/onecall?lat=29.7604&lon=-95.3698&exclude=current,minutely,hourly,alerts&units=imperial&appid={api_key}').json()

    days = pd.date_range(dt.datetime.utcnow().date(), periods=8, freq="D").tolist()
    weather_forecast = {}
    i=0
    for day in weather_response["daily"]:
        weather_day = {
            "temp": np.mean([day["temp"]["min"], day["temp"]["max"]]) if "temp" in day else np.NaN,
            "dewp": day["dew_point"] if "dew_point" in day else np.NaN,
            "slp": day["pressure"] if "pressure" in day else np.NaN,
            "visib": day["visibility"] if "visibility" in day else np.NaN,
            "wdsp": day["wind_speed"] if "wind_speed" in day else np.NaN,
            "max": day["temp"]["max"] if "temp" in day else np.NaN,
            "min": day["temp"]["min"] if "temp" in day else np.NaN,
            "fog": 1 if day["weather"][0]["main"] == "Fog" else 0,
            "rain_drizzle": 1 if day["weather"][0]["main"] in ["Rain", "Drizzle"] else 0,
            "snow_ice_pellets": 1 if day["weather"][0]["main"] == "Snow" else 0,
            "hail": 1 if day["weather"][0]["main"] == "Hail" else 0,
            "thunder": 1 if day["weather"][0]["main"] == "Thunderstorm" else 0
        }
        weather_forecast[days[i]] = weather_day
        i+=1
    

    return pd.DataFrame(weather_forecast).transpose()[0:6].to_json(orient="index")

if __name__ == "__main__":
    app.run(debug=True)
    
