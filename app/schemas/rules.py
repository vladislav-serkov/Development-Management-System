from pydantic import BaseModel


class RulesData(BaseModel):
    extraction: str = ""
    gaps: str = ""
    test_cases: str = ""
    bugs: str = ""
    enrichment: str = ""
