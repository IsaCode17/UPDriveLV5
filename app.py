import os
import requests
from flask import Flask, render_template, request, redirect, url_for, session
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import shutil
import logging
import yt_dlp  # Importar yt-dlp

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'default_secret_key')  # Usar variable de entorno

# Eliminar configuraciones de proxy si existen
os.environ.pop('http_proxy', None)
os.environ.pop('https_proxy', None)

# Cargar las credenciales desde client_secrets.json
CLIENT_SECRETS_FILE = "client_secrets.json"
SCOPES = ['https://www.googleapis.com/auth/drive.file']

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/authorize')
def authorize():
    try:
        flow = Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE,
            scopes=SCOPES,
            redirect_uri=url_for('oauth2callback', _external=True)
        )
    except FileNotFoundError:
        logger.error("El archivo client_secrets.json no se encontró.")
        return "Error: El archivo client_secrets.json no se encontró.", 500

    authorization_url, state = flow.authorization_url(access_type='offline', include_granted_scopes='true')
    session['state'] = state
    logger.info("Redirigiendo al usuario para autorizar la aplicación.")
    return redirect(authorization_url)

@app.route('/oauth2callback')
def oauth2callback():
    state = session.get('state')
    if not state:
        logger.error("Estado de la sesión no encontrado.")
        return "Error: Estado de la sesión no encontrado.", 400

    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        state=state,
        redirect_uri=url_for('oauth2callback', _external=True)
    )
    flow.fetch_token(authorization_response=request.url)

    credentials = flow.credentials
    session['credentials'] = credentials_to_dict(credentials)
    logger.info("Autenticación exitosa. Redirigiendo a la página de carga.")
    return redirect(url_for('upload_page'))

@app.route('/upload_page')
def upload_page():
    return render_template('upload.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'credentials' not in session:
        logger.warning("No hay credenciales en la sesión. Redirigiendo a autorizar.")
        return redirect(url_for('authorize'))

    # Obtener los datos del formulario
    file_url = request.form.get('file_url')
    file_name = request.form.get('file_name')
    youtube_url = request.form.get('youtube_url')  # Nuevo campo para el link de YouTube

    try:
        if youtube_url:
            file_name = "youtube_video.mp4"  # Nombre temporal del video descargado
            download_youtube_video(youtube_url, file_name)
        else:
            if not file_url or not file_name:
                logger.error("URL del archivo o nombre del archivo faltante.")
                return "Error: Se deben proporcionar tanto la URL del archivo como el nombre del archivo.", 400
            # Descargar el archivo
            download_file(file_url, file_name)

        # Subir el archivo a Google Drive
        credentials = Credentials(**session['credentials'])
        drive_service = build('drive', 'v3', credentials=credentials)
        file_metadata = {'name': file_name}
        media = MediaFileUpload(file_name, resumable=True)
        drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        logger.info(f"Archivo {file_name} subido exitosamente a Google Drive.")

        # Eliminar el archivo descargado
        os.remove(file_name)

        return "Archivo subido a Google Drive con éxito!"

    except Exception as e:
        logger.error(f"Error al subir el archivo: {e}")
        return f"Error al subir el archivo: {e}", 500

def download_file(url, filename):
    try:
        logger.info(f"Intentando descargar el archivo desde: {url}")
        response = requests.get(url, stream=True)
        response.raise_for_status()
        with open(filename, 'wb') as file:
            shutil.copyfileobj(response.raw, file)
        logger.info(f"Descarga completa: {filename}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Error al descargar el archivo: {e}")
        raise Exception(f"Error al descargar el archivo: {e}")

# Nueva función para descargar videos de YouTube

def download_youtube_video(url, filename):
    try:
        logger.info(f"Descargando video de YouTube desde: {url}")
        ydl_opts = {
            'outtmpl': '%(title)s.%(ext)s',  # Usa el título original del video
            'format': 'best',  # Puedes ajustar el formato aquí si lo deseas
            'cookiefile': 'cookies.txt'  # Añadir aquí el archivo de cookies
        
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            video_title = ydl.prepare_filename(info_dict)  # Obtén el nombre final del video descargado
        logger.info(f"Video descargado: {video_title}")
        return video_title  # Retornar el nombre del archivo descargado
    except Exception as e:
        logger.error(f"Error al descargar el video de YouTube: {e}")
        raise Exception(f"Error al descargar el video de YouTube: {e}")
        

def credentials_to_dict(credentials):
    return {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    }

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
    
