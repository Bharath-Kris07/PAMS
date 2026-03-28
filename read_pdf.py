import PyPDF2

try:
    reader = PyPDF2.PdfReader('c:/DBMS project/group 16 PAMS.pdf')
    text = [page.extract_text() for page in reader.pages]
    print('\n'.join(text))
except Exception as e:
    import traceback
    traceback.print_exc()
