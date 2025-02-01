import os
import time
import traceback
from flask import Flask, request, send_from_directory, jsonify
from flask_cors import CORS
from config import Config
from cities.views import city_bp
from utils import get_logger


app = Flask(__name__)
cors = CORS(app)

logger = get_logger(__name__)

app.register_blueprint(city_bp, url_prefix=f'{Config.APP_ROOT}/cities')

@app.before_request
def reqbeg():
    request.beg = time.time()

@app.after_request
def reqend(response):
    logger.info('end: %s %s => %s in %.5fs', request.method, request.path, response.status_code, time.time() - request.beg)
    return response

@app.teardown_request
def reqtear(error = None):
    if error:
        logger.exception('error: %s %s in %.5fs:\n%s', request.method, request.path, time.time() - request.beg, error)
        
@app.errorhandler(Exception)
def handle_error(e: Exception):
    """Handle errors and return a message to the client."""
    error_traceback = traceback.format_exc()
    response = {
        'status': 'bad',
        'error': error_traceback.split("\n")[-2]
    }
    logger.error(error_traceback)
    return jsonify(response), 500


@app.route(Config.APP_ROOT)
def hello():
    # do your things here
    return "It works!"


@app.route(f"{Config.APP_ROOT}/file/<file_name>", methods=['GET'])
def return_file(file_name: str):
    return send_from_directory(directory=Config.UPLOAD_FOLDER, path=file_name, as_attachment=True)


if __name__ == "__main__":
    if not os.path.exists(Config.UPLOAD_FOLDER):
        os.mkdir(Config.UPLOAD_FOLDER)
    app.run()