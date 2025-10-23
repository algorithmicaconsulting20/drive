import streamlit as st
import os
import tempfile
from datetime import datetime
from zoneinfo import ZoneInfo
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
import re

# ------------------ Google Drive Authentication (Embedded Credentials + Token) ------------------
SCOPES = ["https://www.googleapis.com/auth/drive"]

# Embedded credentials
CLIENT_CONFIG = {
    "installed": {
        "client_id": "257082126321-j0vjhvdiieej5athd9mvk98trksts1ac.apps.googleusercontent.com",
        "project_id": "clever-cogency-475005-p0",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_secret": "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",
        "redirect_uris": ["http://localhost"]
    }
}

# Embedded token
TOKEN_INFO = {
    "token": "ya29.a0ATi6K2v7fLYqYdLT4e4OYjmP6nNcf6If1qkNnHnWSg3nONNANSD2fDzvVycu4mQw6dLu708neFtMyi3oa3YAMYbYhcWteYkPrtkBIuUZmTGwl6xLl5z_D0MtQsSSV8itev08JCYim7v-QX7z9T3rFMbX9_8FsciUoLjDxSZBXwxnIo6CqocqkVvKQRtorNU9BQmYhtEaCgYKAZkSARMSFQHGX2MiKLo5dcW92YX-kliJBuw-WA0206",
    "refresh_token": "1//0gVKJtFRDzGCkCgYIARAAGBASNwF-L9IriDsc4XdI758pYPYgiw8WkbIT0J_6HjYctXqdik0oIpDTFyj6hAdH9FmcdiZOnN-fio0",
    "token_uri": "https://oauth2.googleapis.com/token",
    "client_id": CLIENT_CONFIG["installed"]["client_id"],
    "client_secret": CLIENT_CONFIG["installed"]["client_secret"],
    "scopes": SCOPES
}

def get_gdrive_service():
    creds = Credentials.from_authorized_user_info(TOKEN_INFO, SCOPES)
    service = build("drive", "v3", credentials=creds)
    return service

# ------------------ Helper: Search for Existing File ------------------
def find_file(service, folder_id, filename):
    query = f"name='{filename}' and '{folder_id}' in parents and trashed=false"
    results = service.files().list(q=query, spaces="drive", fields="files(id, name)").execute()
    items = results.get("files", [])
    return items[0]["id"] if items else None

def list_folders(service):
    results = service.files().list(
        q="mimeType='application/vnd.google-apps.folder' and trashed=false",
        fields="files(id, name)",
        pageSize=1000
    ).execute()
    return results.get("files", [])

def list_files_in_folder(service, folder_id):
    results = service.files().list(
        q=f"'{folder_id}' in parents and trashed=false",
        fields="files(id, name, modifiedTime)",
        orderBy="modifiedTime desc"
    ).execute()
    return results.get("files", [])

# ------------------ Auto Versioning ------------------
def get_next_version(existing_files, base_name):
    pattern = re.compile(rf"{re.escape(base_name)}_v(\d+)")
    max_v = 0
    for f in existing_files:
        match = pattern.search(f['name'])
        if match:
            v = int(match.group(1))
            max_v = max(max_v, v)
    return max_v + 1

def upload_to_drive(service, folder_id, file_path, filename):
    existing_file_id = find_file(service, folder_id, filename)
    media = MediaFileUpload(file_path, resumable=True)

    if existing_file_id:
        service.files().update(fileId=existing_file_id, media_body=media).execute()
        st.success(f"✅ File updated: {filename}")
    else:
        file_metadata = {"name": filename, "parents": [folder_id]}
        service.files().create(body=file_metadata, media_body=media, fields="id").execute()
        st.success(f"✅ New file uploaded: {filename}")

# ------------------ Streamlit App ------------------
def main():
    st.title("📁 Google Drive ZIP Upload with Exact Folder Name & Versioning")

    uploader_name = st.text_input("👤 Enter your name (Uploader):", "")
    service = get_gdrive_service()

    # Fetch folders
    st.subheader("📂 Select Drive Folder")
    folders = list_folders(service)
    folder_options = {f['name']: f['id'] for f in folders}
    if not folder_options:
        st.error("No folders found in your Drive.")
        return
    selected_folder = st.selectbox("Select a folder to upload into:", list(folder_options.keys()))
    folder_id = folder_options[selected_folder]

    # Show existing files
    st.write(f"### Files in '{selected_folder}' folder:")
    files = list_files_in_folder(service, folder_id)
    if files:
        for f in files:
            st.write(f"- {f['name']} (Last modified: {f['modifiedTime']})")
    else:
        st.info("This folder is empty.")

    uploaded_file = st.file_uploader("Upload a ZIP file", type=["zip"])

    if st.button("🚀 Upload to Drive"):
        if not uploader_name:
            st.error("Please enter your name before uploading.")
            return
        if not uploaded_file:
            st.error("Please upload a ZIP file.")
            return

        # --- File naming must match folder ---
        base_name = selected_folder
        uploaded_base_name = os.path.splitext(uploaded_file.name)[0]
        if uploaded_base_name.lower() != base_name.lower():
            st.error(f"❌ File name must exactly match folder name: '{base_name}'")
            return

        # --- Save temp file ---
        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp_file:
            tmp_file.write(uploaded_file.read())
            temp_name = tmp_file.name

        # --- Determine next version ---
        next_v = get_next_version(files, base_name)
        timestamp = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y%m%d_%H%M%S")
        new_filename = f"{base_name}_v{next_v}_{uploader_name}_{timestamp}.zip"
        new_path = os.path.join(tempfile.gettempdir(), new_filename)
        os.replace(temp_name, new_path)

        upload_to_drive(service, folder_id, new_path, new_filename)

        # Clean up temp file
        if os.path.exists(new_path):
            os.remove(new_path)

if __name__ == "__main__":
    main()
