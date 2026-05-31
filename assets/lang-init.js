(function(){
  function browserLang(){
    var langs = navigator.languages && navigator.languages.length ? navigator.languages : [navigator.language || ''];
    for(var i = 0; i < langs.length; i += 1){
      if(String(langs[i] || '').toLowerCase().indexOf('ru') === 0) return 'ru';
    }
    return 'en';
  }
  try{
    var saved = localStorage.getItem('lang');
    var lang = (saved === 'ru' || saved === 'en') ? saved : browserLang();
    document.documentElement.lang = lang;
    document.documentElement.classList.toggle('lang-en', lang === 'en');
  }catch(e){
    document.documentElement.lang = browserLang();
    document.documentElement.classList.toggle('lang-en', document.documentElement.lang === 'en');
  }
})();
