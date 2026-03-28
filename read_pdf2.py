import fitz  # PyMuPDF

try:
    doc = fitz.open("c:/DBMS project/group 16 PAMS.pdf")
    text = ""
    for page in doc:
        text += page.get_text()
    
    with open("pdf_text_output.txt", "w", encoding="utf-8") as f:
        f.write(text)
    
    print("Success")
except Exception as e:
    import traceback
    traceback.print_exc()
