"""Validate and transactionally import the reviewed four-provider starting snapshot."""
import argparse
import json
from pathlib import Path

from .config import ROOT, Settings
from .repository import Repository
from .schemas import DiscoveryProvider


def load_seed(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(data, list):
        raise ValueError('Seed must be a provider list.')
    records = [DiscoveryProvider.model_validate(record) for record in data]
    if len({p.id for p in records}) != len(records):
        raise ValueError('Seed contains duplicate IDs.')
    for provider in records:
        if provider.whatsappConfirmed and not (provider.whatsappNumber and provider.whatsappSourceUrl and provider.whatsappCheckedAt):
            raise ValueError('Confirmed contact needs supporting evidence metadata.')
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file', type=Path, default=ROOT / 'backend/data/providers.json')
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args()
    try:
        providers = load_seed(args.file)
        if not args.validate_only:
            repository = Repository(Settings.from_env().database_path)
            repository.initialize()
            repository.import_providers(providers)
        print(f'{"Validated" if args.validate_only else "Imported"} {len(providers)} starting providers.')
    except (ValueError, OSError) as error:
        parser.exit(1, f'Import failed: {type(error).__name__}. Check seed fields and schema.\n')


if __name__ == '__main__':
    main()
