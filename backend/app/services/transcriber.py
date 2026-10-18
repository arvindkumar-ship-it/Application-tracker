import base64
import io
from pathlib import Path
from PIL import Image
import pymupdf as fitz
from app.llm.client import LLMClient


async def transcribe_files(paths):
    pages=[]
    for name in paths:
        path=Path(name)
        if path.suffix=='.pdf':
            document=fitz.open(path)
            if document.page_count>30: raise ValueError('PDF exceeds the 30-page processing limit')
            extracted='\n'.join(page.get_text() for page in document)
            if len(extracted.strip())>=200:
                pages.append(extracted);document.close();continue
            images=[page.get_pixmap(matrix=fitz.Matrix(1.5,1.5)).tobytes('png') for page in document]
            document.close()
        else:
            with Image.open(path) as image:
                image.thumbnail((2400,2400));buffer=io.BytesIO();image.convert('RGB').save(buffer,format='PNG');images=[buffer.getvalue()]
        for image in images:
            block={'type':'image','source':{'type':'base64','media_type':'image/png','data':base64.b64encode(image).decode()}}
            pages.append(await LLMClient().complete_text('transcribe',{},images=[block]))
    return '\n--- IMAGE BREAK ---\n'.join(pages)
