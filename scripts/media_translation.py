"""Cached optional offline translation; manual translations always win."""
import hashlib
import json
import os
import re


class MediaTranslator:
    def __init__(self, path):
        self.path = path
        self.cache = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        self.status = 'not_needed'
        self._translation = None
        self._attempted = False
        self._changed = False

    def ensure(self):
        if self._attempted:
            return self._translation is not None
        self._attempted = True
        try:
            import argostranslate.package as package
            import argostranslate.translate as translate
            installed = package.get_installed_packages()
            model = next((p for p in installed if p.from_code == 'ru' and p.to_code == 'en'), None)
            if model is None and os.environ.get('MEDIA_INSTALL_ARGOS', '1') == '1':
                package.update_package_index()
                model = next((p for p in package.get_available_packages() if p.from_code == 'ru' and p.to_code == 'en'), None)
                if model:
                    package.install_from_path(model.download())
            if model is None:
                self.status = 'ru_en_model_unavailable'
                return False
            languages = translate.get_installed_languages()
            source = next(p for p in languages if p.code == 'ru')
            target = next(p for p in languages if p.code == 'en')
            self._translation = source.get_translation(target)
            # Verify the actual installed language pair, not just the package name.
            probe = self._translation.translate('Научное исследование')
            if not probe.strip() or re.search('[А-Яа-яЁё]', probe):
                self._translation = None
                self.status = 'model_validation_failed'
                return False
            self.status = 'argos_ru_en'
            return True
        except Exception as exc:
            self.status = 'unavailable_' + type(exc).__name__
            return False

    def enrich(self, record):
        for field in ('title', 'description'):
            if record.get(field + '_en'):
                continue
            original = record.get(field + '_ru') or record.get(field) or ''
            if not original:
                continue
            if not re.search('[А-Яа-яЁё]', original):
                record[field + '_en'] = original
                continue
            key = hashlib.sha256(('ru:en:' + original).encode()).hexdigest()
            cached = self.cache.get(key)
            if cached:
                record[field + '_en'] = cached['translation']
                record[field + '_en_origin'] = 'cached_argos_ru_en'
                continue
            if not self.ensure():
                continue  # The existing UI falls back to the Russian text.
            try:
                result = self._translation.translate(original).strip()
                if result and result != original and not re.search('[А-Яа-яЁё]', result):
                    record[field + '_en'] = result
                    record[field + '_en_origin'] = 'argos_ru_en'
                    self.cache[key] = {'original': original, 'translation': result, 'model': 'ru_en'}
                    self._changed = True
            except Exception as exc:
                self.status = 'translation_failed_' + type(exc).__name__

    def save(self):
        if self._changed:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            staged = self.path.with_suffix('.tmp')
            staged.write_text(json.dumps(self.cache, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            staged.replace(self.path)
