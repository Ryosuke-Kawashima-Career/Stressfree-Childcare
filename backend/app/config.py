"""Environment-backed local service configuration; secrets never appear in repr."""
from dataclasses import dataclass, field
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Reviewed official provider/government domains; server operators may extend this list.
SOURCE_DOMAINS = (
    'medanta.org', 'artemishospitals.com', 'udayancare.org', 'fortishealthcare.com',
    'maxhealthcare.in', 'manipalhospitals.com', 'narayanahealth.org', 'ckbirlahospital.com',
    'parashealth.com', 'cloudninecare.com', 'apollohospitals.com', 'gurugram.gov.in',
    'haryana.gov.in', 'nhm.gov.in', 'pratham.org', 'deepalaya.org', 'smilefoundationindia.org',
    'lotuspetalfoundation.org', 'shivnadarschool.edu.in', 'shikshantarschool.com',
    'heritagexperiential.org', 'dpsgurgaon.org',
)


@dataclass(frozen=True)
class Settings:
    database_path: Path = ROOT / 'backend/data/caregiving.sqlite3'
    openai_api_key: str = field(default='', repr=False)
    ai_model: str = 'gpt-4.1-mini'
    source_domains: tuple[str, ...] = SOURCE_DOMAINS
    ai_timeout_seconds: float = 30
    ai_max_results: int = 5
    ai_max_output_tokens: int = 6000
    ai_requests_per_minute: int = 10
    ai_max_inflight: int = 4
    cache_ttl_seconds: int = 86400

    def __post_init__(self):
        bounds = [('ai_timeout_seconds', 0.001, 30), ('ai_max_results', 1, 20),
                  ('ai_max_output_tokens', 256, 12000), ('ai_requests_per_minute', 1, 100),
                  ('ai_max_inflight', 1, 10), ('cache_ttl_seconds', 1, 86400)]
        for name, low, high in bounds:
            if not low <= getattr(self, name) <= high:
                raise ValueError(f'{name} must be between {low} and {high}')

    @classmethod
    def from_env(cls):
        value = os.environ.get('CARE_LEARN_DB_PATH')
        options = dict(database_path=Path(value).expanduser().resolve()) if value else {}
        options['openai_api_key'] = os.environ.get('OPENAI_API_KEY', '')
        options['ai_model'] = os.environ.get('CARE_LEARN_AI_MODEL', 'gpt-4.1-mini')
        domains = os.environ.get('CARE_LEARN_SOURCE_DOMAINS')
        if domains:
            options['source_domains'] = tuple(d.strip().lower() for d in domains.split(',') if d.strip())
        for environment, name in [
            ('CARE_LEARN_AI_TIMEOUT_SECONDS', 'ai_timeout_seconds'),
            ('CARE_LEARN_AI_MAX_RESULTS', 'ai_max_results'),
            ('CARE_LEARN_AI_MAX_OUTPUT_TOKENS', 'ai_max_output_tokens'),
            ('CARE_LEARN_AI_REQUESTS_PER_MINUTE', 'ai_requests_per_minute'),
            ('CARE_LEARN_AI_MAX_INFLIGHT', 'ai_max_inflight'),
            ('CARE_LEARN_CACHE_TTL_SECONDS', 'cache_ttl_seconds')]:
            if environment in os.environ:
                options[name] = float(os.environ[environment]) if name == 'ai_timeout_seconds' else int(os.environ[environment])
        return cls(**options)
