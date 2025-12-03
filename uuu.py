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
    permission = {'type': 'anyone', 'role': 'reader'}
    try:
        service.permissions().create(fileId=file_id, body=permission).execute()
    except Exception as e:
        st.warning(f"⚠️ Could not make file public: {e}")

def list_folders(service):
    results = service.files().list(
        q="mimeType='application/vnd.google-apps.folder' and trashed=false",
        fields="files(id, name)", pageSize=1000
    ).execute()
    return results.get("files", [])

def list_files_in_folder(service, folder_id):
    results = service.files().list(
        q=f"'{folder_id}' in parents and trashed=false",
        fields="files(id, name, modifiedTime, webViewLink)",
        orderBy="modifiedTime desc"
    ).execute()
    return results.get("files", [])

def find_file(service, folder_id, filename):
    query = f"name='{filename}' and '{folder_id}' in parents and trashed=false"
    results = service.files().list(q=query, spaces="drive", fields="files(id, name)").execute()
    items = results.get("files", [])
    return items[0]["id"] if items else None

def delete_file(service, file_id):
    service.files().delete(fileId=file_id).execute()

def get_next_version(existing_files, base_name):
    pattern = re.compile(rf"{re.escape(base_name)}_v(\d+)")
    max_v = 0
    for f in existing_files:
        m = pattern.search(f['name'])
        if m:
            max_v = max(max_v, int(m.group(1)))
    return max_v + 1

def upload_to_drive(service, folder_id, file_path, filename):
    existing_file_id = find_file(service, folder_id, filename)
    media = MediaFileUpload(file_path, resumable=True)

    if existing_file_id:
        updated = service.files().update(fileId=existing_file_id, media_body=media, fields="id").execute()
        make_file_public(service, updated.get("id"))
        st.success(f"✅ File updated: {filename}")
    else:
        metadata = {"name": filename, "parents": [folder_id]}
        uploaded = service.files().create(body=metadata, media_body=media, fields="id").execute()
        make_file_public(service, uploaded.get("id"))
        st.success(f"✅ New file uploaded: {filename}")

def create_new_folder(service, folder_name):
    metadata = {"name": folder_name, "mimeType": "application/vnd.google-apps.folder"}
    folder = service.files().create(body=metadata, fields="id, name").execute()
    return folder["id"]

# ------------------ Streamlit UI ------------------
def main():
    st.title("📁 Google Drive ZIP Upload with Versioning")

    uploader_name = st.text_input("👤 Enter your name:", "")
    service = get_gdrive_service()

    # ---------------- FOLDER SELECTION ----------------
    st.subheader("📂 Select Drive Folder")

    col1, col2 = st.columns([4, 1])

    with col1:
        folders = list_folders(service)
        folder_options = {f["name"]: f["id"] for f in folders}
        selected_folder = st.selectbox("Choose a folder:", list(folder_options.keys()))

    with col2:
        if st.button("➕"):
            st.session_state["create_folder"] = True

    # Create new folder popup
    if st.session_state.get("create_folder"):
        new_name = st.text_input("New Folder Name:")
        if st.button("Create"):
            if not new_name.strip():
                st.error("Folder name cannot be empty.")
            elif new_name in folder_options:
                st.error("Folder already exists.")
            else:
                create_new_folder(service, new_name)
                st.success(f"Folder '{new_name}' created!")
                st.session_state["create_folder"] = False
                st.rerun()

        if st.button("Cancel"):
            st.session_state["create_folder"] = False
            st.rerun()

    folder_id = folder_options[selected_folder]

    # ---------------- SHOW FILES WITH DELETE OPTION ----------------
    st.write(f"### Files inside '{selected_folder}' folder:")
    files = list_files_in_folder(service, folder_id)

    if files:
        for f in files:
            fname = f["name"]
            ftime = f["modifiedTime"]
            file_id = f["id"]
            link = f"https://drive.google.com/uc?id={file_id}&export=download"

            colA, colB, colC = st.columns([5, 2, 1])

            with colA:
                st.write(f"📦 **{fname}**\n🕒 {ftime}")

            with colB:
                st.markdown(f"[⬇️ Download]({link})", unsafe_allow_html=True)

            with colC:
                if st.button("🗑️ Delete", key=f"del_{file_id}"):
                    delete_file(service, file_id)
                    st.success(f"🗑️ Deleted: {fname}")
                    st.rerun()
    else:
        st.info("This folder is empty.")

    # ---------------- UPLOAD SECTION ----------------
    uploaded_file = st.file_uploader("Upload ZIP File", type=["zip"])

    if st.button("🚀 Upload"):
        if not uploader_name:
            st.error("Enter your name.")
            return
        if not uploaded_file:
            st.error("Upload a ZIP file.")
            return

        base_name = selected_folder.strip()
        uploaded_base = os.path.splitext(uploaded_file.name)[0]

        if not uploaded_base.lower().startswith(base_name.lower()):
            st.error(f"❌ File name must start with folder name '{base_name}'")
            return

        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
            tmp.write(uploaded_file.read())
            temp_path = tmp.name

        next_v = get_next_version(files, base_name)
        timestamp = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y%m%d_%H%M%S")

        clean_name = os.path.splitext(uploaded_file.name)[0]
        new_filename = f"{clean_name}_v{next_v}_{uploader_name}_{timestamp}.zip"
        final_path = os.path.join(tempfile.gettempdir(), new_filename)

        os.replace(temp_path, final_path)

        upload_to_drive(service, folder_id, final_path, new_filename)

        os.remove(final_path)

if __name__ == "__main__":
    main()
