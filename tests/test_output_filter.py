import pytest

from aurora.output_filter import redact


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("Reserva RSV-4821 confirmada", "Reserva [dado restrito] confirmada"),
        ("Visitante Marina Duarte confirmado", "Visitante [dado restrito] confirmado"),
        ("Apartamento 302 liberado", "Apartamento [dado restrito] liberado"),
        ("Data 2030-03-02 e codigo AUR-0302", "Data 2030-03-02 e codigo AUR-0302"),
        ("Apartamento 101", "Apartamento 101"),
    ],
)
def test_redacts_other_apartments(texto, esperado):
    assert redact(texto, terms=["RSV-4821", "Marina Duarte"], numbers=["302"]) == esperado
