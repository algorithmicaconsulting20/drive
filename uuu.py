import streamlit as st
import os
import tempfile
from datetime import datetime
from zoneinfo import ZoneInfo
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
import re

# ------------------ Google Drive Authentication ------------------
SCOPES = ["https://www.googleapis.com/auth/drive"]

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

TOKEN_INFO = {
    "token": "ya29.a0ATi6K2v7fLYqYdLT4e4OYjmP6nNcf6If1qkNnHnWSg3nONNANSD2fDzvVycu4mQw6dLu708neFtMyi3oa3YAMYbYhcWteYkPrtkBIuUZmTGwl6xLl5z_D0MtQsSSV8itev08JCYim7v-QX7z9T3rFMbX9_8FsciUoLjDxSZBXwxnIo6CqocqkVvKQRtorNU9BQmYhtEaCgYKAZkSARMSFQHGX2MiKLo5dcW92YX-kliJBuw-WA0206",
    "refresh_token": "1//0gVKJtFRDzGCkCgYIARAAGBASNwF-L9IriDsc4XdI758pYPYgiw8WkbIT0J_6HjYctXqdik0oIpDTFyj6hAdH9FmcdiZOnN-fio0",
    "token_uri": "https://oauth2.googleapis.com/token",
    "client_id": CLIENT_CONFIG["installed"]["client_id"],
    "client_secret": CLIENT_CONFIG["installed"]["client_secret"],
    "scopes": SCOPES
}

# ------------------ Google Drive Setup ------------------
def get_gdrive_service():
    creds = Credentials.from_authorized_user_info(TOKEN_INFO, SCOPES)
    service = build("drive", "v3", credentials=creds)
    return service

# ------------------ Helpers ------------------
def make_file_public(service, file_id):
    """Make a file publicly accessible (anyone with the link)."""
    permission = {'type': 'anyone', 'role': 'reader'}
    try:
        service.permissions().create(fileId=file_id, body=permission).execute()
    except Exception as e:
        st.warning(f"⚠️ Could not make file public: {e}")

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
        fields="files(id, name, modifiedTime, webViewLink)",
        orderBy="modifiedTime desc"
    ).execute()
    return results.get("files", [])

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
    """Uploads file to Drive and makes it public."""
    existing_file_id = find_file(service, folder_id, filename)
    media = MediaFileUpload(file_path, resumable=True)

    if existing_file_id:
        updated = service.files().update(fileId=existing_file_id, media_body=media, fields="id").execute()
        make_file_public(service, updated.get("id"))
        st.success(f"✅ File updated: {filename}")
    else:
        file_metadata = {"name": filename, "parents": [folder_id]}
        uploaded = service.files().create(body=file_metadata, media_body=media, fields="id").execute()
        make_file_public(service, uploaded.get("id"))
        st.success(f"✅ New file uploaded: {filename}")

# ------------------ Streamlit App ------------------
def main():
    st.title("📁 Google Drive ZIP Upload with Versioning + Download Option (Public Access)")

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
    st.write(f"### Existing Files in '{selected_folder}' Folder:")
    files = list_files_in_folder(service, folder_id)
    if files:
        for f in files:
            file_name = f['name']
            modified_time = f['modifiedTime']
            file_id = f['id']
            download_link = f"https://drive.google.com/uc?id={file_id}&export=download"
            col1, col2 = st.columns([4, 1])
            with col1:
                st.write(f"📦 **{file_name}**  \n🕒 *Modified:* {modified_time}")
            with col2:
                st.markdown(f"[⬇️ Download]({download_link})", unsafe_allow_html=True)
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

        # --- ✅ Relaxed Rule: File name must start with folder name ---
        base_name = selected_folder.strip()
        uploaded_base_name = os.path.splitext(uploaded_file.name)[0].strip()

        if not uploaded_base_name.lower().startswith(base_name.lower()):
            st.error(f"❌ File name must start with the folder name: '{base_name}'")
            return

        # Save temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp_file:
            tmp_file.write(uploaded_file.read())
            temp_name = tmp_file.name

        # Determine next version
        next_v = get_next_version(files, base_name)
        timestamp = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y%m%d_%H%M%S")
        new_filename = f"{base_name}_v{next_v}_{uploader_name}_{timestamp}.zip"
        new_path = os.path.join(tempfile.gettempdir(), new_filename)
        os.replace(temp_name, new_path)

        upload_to_drive(service, folder_id, new_path, new_filename)

        # Clean up
        if os.path.exists(new_path):
            os.remove(new_path)

if __name__ == "__main__":
    main()
