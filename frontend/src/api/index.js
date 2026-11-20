import api from './client';

export const getHealth = () => api.get('/health');
export const getNostrStatus = () => api.get('/api/nostr/status');
export const getNostrMerchants = (limit = 50) => api.get('/api/nostr/merchants', { params: { limit } });
export const getMyMerchant = () => api.get('/api/merchants/me');
export const getProducts = (merchantId) => api.get('/api/products', { params: { merchant_id: merchantId } });
export const getUnsignedNostrListing = (productId) => api.get('/api/nostr/listings/unsigned', { params: { product_id: productId } });
export const publishNostrListing = (productId, event) => api.post('/api/nostr/publish', { product_id: productId, event });

export const register = (data) => api.post('/api/auth/register', data);
export const login = (data) => api.post('/api/auth/login', data);
export const logout = () => api.post('/api/auth/logout');
export const getMe = () => api.get('/api/auth/me');

export const getMarketplace = (search = '', category = '') =>
  api.get('/api/marketplace', { params: { search, category } });

export const getMerchants = () => api.get('/api/merchants');

export const createMerchant = (data) => api.post('/api/merchants', data);

export const createProduct = (data) => api.post('/api/products', data);

export const runAgents = (query, location, sessionId) =>
  api.post('/api/agents/run', { query, location, session_id: sessionId });

export const getSessions = () => api.get('/api/agents/sessions');

export const getSession = (sessionId) => api.get(`/api/agents/sessions/${sessionId}`);

export const getSessionMessages = (sessionId) =>
  api.get(`/api/agents/sessions/${sessionId}/messages`);

export const getNegotiation = (id) => api.get(`/api/negotiations/${id}`);

export const approveNegotiation = (id) => api.post(`/api/negotiations/${id}/approve`);

export const createInvoice = (data) => api.post('/api/lightning/invoices', data);

export const checkInvoice = (id) => api.get(`/api/lightning/invoices/${id}`);
export const simulateInvoicePayment = (id) => api.post(`/api/lightning/invoices/${id}/simulate-payment`);
export const submitMerchantSettlement = (id, bolt11) => api.post(`/api/transactions/${id}/settlement`, { bolt11 });
export const getMerchantSettlement = (id) => api.get(`/api/transactions/${id}/settlement`);

export const getTransactions = () => api.get('/api/transactions');

export const getSecurityChecks = () => api.get('/api/security/checks');
