"""Create a portable submission archive without environments or machine-specific files."""
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def package(output=None):
    output = output or ROOT/'dist'/'parts-inventory-case-study.zip'
    files = [ROOT/name for name in ('app.py','run.sh','requirements.txt','README.md',
             'IMPLEMENTATION_PLAN.md','.gitignore','.gitattributes','.streamlit/config.toml',
             'review_browser.sh','requirements-browser.txt',
             'Case_Study_Dataset.csv','Data & AI Engineer - Case Study.docx.md')]
    for directory in ('src','tests','scripts','reports','docs'):
        files += [p for p in (ROOT/directory).rglob('*') if p.is_file()
                  and '__pycache__' not in p.parts and (p.suffix in {'.py','.md','.csv','.json','.jsonl'}
                       or (p.suffix == '.png' and p.parent.name == 'screenshots'))
                  and p.name not in {'INDEPENDENT_REVIEW.md', 'BOSS_READINESS_REVIEW.md', 'attempts.json'}]
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for path in sorted(set(files)):
            info = zipfile.ZipInfo('parts-inventory-case-study/'+path.relative_to(ROOT).as_posix(),
                                   date_time=(2026,11,12,0,0,0))
            info.create_system = 3
            info.external_attr = (0o100755 if path.name in {'run.sh','review_browser.sh'} else 0o100644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info,path.read_bytes())
    print(output)
    return output


if __name__=='__main__':
    package()
