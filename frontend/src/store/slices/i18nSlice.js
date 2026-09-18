import { createSlice } from '@reduxjs/toolkit';
const SUPPORTED = ['en','hi','ta','te','mr','bn','gu','kn'];
function detect() {
  try { const s = localStorage.getItem('gg_lang'); if (s && SUPPORTED.includes(s)) return s; } catch {}
  return 'en';
}
const i18nSlice = createSlice({
  name: 'i18n',
  initialState: { lang: detect() },
  reducers: {
    setLang(state, { payload }) {
      if (SUPPORTED.includes(payload)) {
        state.lang = payload;
        try { localStorage.setItem('gg_lang', payload); } catch {}
      }
    },
  },
});
export const { setLang } = i18nSlice.actions;
export const selectLang = (s) => s.i18n.lang;
export const LANG_NAMES = {
  en: 'English', hi: 'हिंदी', ta: 'தமிழ்', te: 'తెలుగు',
  mr: 'मराठी', bn: 'বাংলা', gu: 'ગુજરાતી', kn: 'ಕನ್ನಡ',
};
export default i18nSlice.reducer;
