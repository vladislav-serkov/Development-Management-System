from bs4 import BeautifulSoup

from app.services.confluence import _table_grid
from app.services.table_mapping import table_to_spec_table

# Shape of [flp-ewallet-adapter] POST /provider/getStatuses response table: nesting
# indent cells and a shared "Источник" cell span several rows via rowspan.
ROWSPAN_TABLE = """
<table><tbody>
<tr><th colspan="3">Поле</th><th>Обяз.</th><th>Описание</th><th>Тип данных</th><th>Источник</th></tr>
<tr><td colspan="3">errorCode</td><td>R</td><td>Код</td><td>number</td><td>Описан в сценарии</td></tr>
<tr><td colspan="3">paymentStatuses[]</td><td>R</td><td></td><td>array</td><td>Описан в сценарии</td></tr>
<tr><td rowspan="5"></td><td colspan="2">paymentId</td><td>R</td><td>Идентификатор</td><td>string</td><td>payment.md_order</td></tr>
<tr><td colspan="2">paymentStatus</td><td>R</td><td>Статус</td><td>string</td><td>Описано в сценарии</td></tr>
<tr><td colspan="2">paymentDetails[]</td><td>O</td><td></td><td>array</td><td rowspan="3">Не заполняется</td></tr>
<tr><td rowspan="2"></td><td>name</td><td>R</td><td>Имя</td><td>string</td></tr>
<tr><td>value</td><td>R</td><td>Значение</td><td>string</td></tr>
</tbody></table>
"""


def _grid(html: str):
    return _table_grid(BeautifulSoup(html, "html.parser").find("table"))


def test_rowspan_cells_occupy_rows_below():
    headers, rows, _, _ = _grid(ROWSPAN_TABLE)

    assert headers == ["Поле", "", "", "Обяз.", "Описание", "Тип данных", "Источник"]
    assert rows[3] == ["", "paymentStatus", "", "R", "Статус", "string", "Описано в сценарии"]
    assert rows[5] == ["", "", "name", "R", "Имя", "string", "Не заполняется"]
    assert rows[6] == ["", "", "value", "R", "Значение", "string", "Не заполняется"]


def test_rowspan_keeps_nesting_and_columns():
    headers, rows, row_links, deprecated = _grid(ROWSPAN_TABLE)
    table = table_to_spec_table(
        {"headers": headers, "rows": rows, "row_links": row_links, "deprecated_rows": deprecated}
    )

    assert [f.name for f in table.fields] == ["errorCode", "paymentStatuses[]"]
    statuses = table.fields[1]
    assert [f.name for f in statuses.children] == ["paymentId", "paymentStatus", "paymentDetails[]"]
    details = statuses.children[2]
    assert [f.name for f in details.children] == ["name", "value"]
    assert details.children[1].cells == ["R", "Значение", "string", "Не заполняется"]
