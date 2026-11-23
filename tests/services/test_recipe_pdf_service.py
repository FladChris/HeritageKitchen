from app.services.recipe_pdf_service import pdf_filename


def test_safe_unicode_pdf_filename():
    result = pdf_filename('Öl/"Kuchen"\r\nTest\\')
    assert '\n' not in result and '\r' not in result
    assert "filename*=UTF-8''%C3%96l-" in result
    assert 'filename="Ol--Kuchen---Test-.pdf"' in result
