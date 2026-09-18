import { createSlice } from '@reduxjs/toolkit';

const storedToken = localStorage.getItem('rashtrabid_token') || localStorage.getItem('gemguard_token') || localStorage.getItem('token');
const storedRole = localStorage.getItem('role');
const storedName = localStorage.getItem('user_name');
const storedEmail = localStorage.getItem('user_email');

const initialState = {
  token: storedToken,
  role: storedRole || null,
  user: storedToken ? {
    role: storedRole || 'PROCUREMENT_OFFICER',
    name: storedName || 'Officer',
    email: storedEmail || 'officer@cpcl.gov.in',
  } : null,
  isAuthenticated: !!storedToken,
};

const authSlice = createSlice({
  name: 'auth',
  initialState,
  reducers: {
    loginSuccess(state, action) {
      const { token, role, name, email, department } = action.payload;
      state.token = token;
      state.role = role;
      state.user = { role, name: name || 'Officer', email: email || '', department: department || '' };
      state.isAuthenticated = true;

      // Synchronize across storage keys
      localStorage.setItem('rashtrabid_token', token);
      localStorage.setItem('gemguard_token', token);
      localStorage.setItem('token', token);
      localStorage.setItem('role', role);
      if (name) localStorage.setItem('user_name', name);
      if (email) localStorage.setItem('user_email', email);
    },
    logout(state) {
      state.token = null;
      state.role = null;
      state.user = null;
      state.isAuthenticated = false;

      localStorage.removeItem('rashtrabid_token');
      localStorage.removeItem('gemguard_token');
      localStorage.removeItem('token');
      localStorage.removeItem('role');
      localStorage.removeItem('user_name');
      localStorage.removeItem('user_email');
    },
  },
});

export const { loginSuccess, logout } = authSlice.actions;
export default authSlice.reducer;

