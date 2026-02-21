"""
File Upload Handler - Document Processing and Context Integration
Created with love by Xeeker & Claude - February 2026

Handles uploading and processing various file types for AI context.

BUG FIX: Heavy dependencies (PyPDF2, docx, PIL, pytesseract) are now
lazy-loaded per method so a missing optional library doesn't break
plain text uploads.
"""

import os
import json
from datetime import datetime
from typing import Dict, List, Tuple


class FileUploadHandler:
    """Handle file uploads and extract content for AI context"""

    def __init__(self, upload_dir: str = None):
        if upload_dir is None:
            # Default relative to this file's location
            base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            upload_dir = os.path.join(base, 'data', 'uploads')

        self.upload_dir = upload_dir
        os.makedirs(upload_dir, exist_ok=True)

        self.supported_extensions = {
            '.txt':  self.read_text,
            '.md':   self.read_text,
            '.py':   self.read_text,
            '.js':   self.read_text,
            '.json': self.read_text,
            '.html': self.read_text,
            '.css':  self.read_text,
            '.cpp':  self.read_text,
            '.c':    self.read_text,
            '.java': self.read_text,
            '.pdf':  self.read_pdf,
            '.docx': self.read_docx,
            '.doc':  self.read_docx,
            '.png':  self.read_image_ocr,
            '.jpg':  self.read_image_ocr,
            '.jpeg': self.read_image_ocr,
        }

    def save_upload(self, file_data: bytes, filename: str) -> Tuple[bool, str, str]:
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            safe_filename = f"{timestamp}_{filename}"
            filepath = os.path.join(self.upload_dir, safe_filename)
            with open(filepath, 'wb') as f:
                f.write(file_data)
            return True, filepath, f"File saved: {safe_filename}"
        except Exception as e:
            return False, "", f"Failed to save file: {str(e)}"

    def process_file(self, filepath: str) -> Tuple[bool, Dict]:
        try:
            _, ext = os.path.splitext(filepath)
            ext = ext.lower()
            if ext not in self.supported_extensions:
                return False, {'error': f'Unsupported file type: {ext}'}
            content = self.supported_extensions[ext](filepath)
            stat = os.stat(filepath)
            metadata = {
                'filename': os.path.basename(filepath),
                'size_bytes': stat.st_size,
                'uploaded': datetime.now().isoformat(),
                'type': ext[1:]
            }
            return True, {'content': content, 'metadata': metadata}
        except Exception as e:
            return False, {'error': f'Failed to process file: {str(e)}'}

    def read_text(self, filepath: str) -> str:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()

    def read_pdf(self, filepath: str) -> str:
        """BUG FIX: Lazy import so missing PyPDF2 only breaks PDFs, not everything"""
        try:
            import PyPDF2
            text = []
            with open(filepath, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    text.append(page.extract_text())
            return '\n\n'.join(text)
        except ImportError:
            return "[PDF support not available - install PyPDF2]"
        except Exception as e:
            return f"[PDF reading error: {str(e)}]"

    def read_docx(self, filepath: str) -> str:
        """BUG FIX: Lazy import"""
        try:
            import docx
            doc = docx.Document(filepath)
            return '\n\n'.join(p.text for p in doc.paragraphs)
        except ImportError:
            return "[DOCX support not available - install python-docx]"
        except Exception as e:
            return f"[DOCX reading error: {str(e)}]"

    def read_image_ocr(self, filepath: str) -> str:
        """BUG FIX: Lazy import"""
        try:
            from PIL import Image
            import pytesseract
            image = Image.open(filepath)
            return pytesseract.image_to_string(image).strip()
        except ImportError:
            return "[Image OCR not available - install Pillow and pytesseract]"
        except Exception as e:
            return f"[Image OCR error: {str(e)}]"

    def get_recent_uploads(self, limit: int = 10) -> List[Dict]:
        try:
            files = []
            for filename in os.listdir(self.upload_dir):
                filepath = os.path.join(self.upload_dir, filename)
                if os.path.isfile(filepath):
                    stat = os.stat(filepath)
                    files.append({
                        'filename': filename,
                        'size_bytes': stat.st_size,
                        'modified': datetime.fromtimestamp(stat.st_mtime).isoformat()
                    })
            files.sort(key=lambda x: x['modified'], reverse=True)
            return files[:limit]
        except Exception as e:
            print(f"Error getting uploads: {e}")
            return []

    def delete_upload(self, filename: str) -> Tuple[bool, str]:
        try:
            filepath = os.path.join(self.upload_dir, filename)
            if os.path.exists(filepath):
                os.remove(filepath)
                return True, f"Deleted: {filename}"
            return False, "File not found"
        except Exception as e:
            return False, f"Failed to delete: {str(e)}"

    def format_for_context(self, content_dict: Dict) -> str:
        if 'error' in content_dict:
            return f"[File processing error: {content_dict['error']}]"
        metadata = content_dict['metadata']
        content = content_dict['content']
        return f"""--- Uploaded Document ---
Filename: {metadata['filename']}
Type: {metadata['type']}
Size: {metadata['size_bytes']} bytes
Uploaded: {metadata['uploaded']}

Content:
{content}
--- End of Document ---
"""
