class InvestmentTracker {
    constructor() {
        this.apiBase = '/api';
        this.user = null;
        this.ledgers = [];
        this.accounts = [];
        this.currentLedgerId = null;
        this.currentAccountId = null;
        this.transactionsPage = 1;
        this.transactionsPerPage = 20;
        this.init();
    }

    init() {
        this.bindEvents();
        this.checkAuth();
    }

    bindEvents() {
        document.getElementById('login-form').addEventListener('submit', (e) => this.handleLogin(e));
        document.getElementById('register-form').addEventListener('submit', (e) => this.handleRegister(e));
        document.getElementById('show-register').addEventListener('click', (e) => {
            e.preventDefault();
            this.showPage('register-page');
        });
        document.getElementById('show-login').addEventListener('click', (e) => {
            e.preventDefault();
            this.showPage('login-page');
        });
        document.getElementById('logout-btn').addEventListener('click', () => this.handleLogout());
        document.getElementById('sidebar-toggle').addEventListener('click', () => this.toggleSidebar());

        document.querySelectorAll('.nav-item').forEach(item => {
            item.addEventListener('click', (e) => {
                const page = e.currentTarget.dataset.page;
                this.navigateTo(page);
            });
        });

        document.getElementById('ledger-select').addEventListener('change', (e) => {
            this.currentLedgerId = e.target.value ? parseInt(e.target.value) : null;
            this.loadAccounts();
            this.loadDashboard();
        });

        document.getElementById('account-select').addEventListener('change', (e) => {
            this.currentAccountId = e.target.value ? parseInt(e.target.value) : null;
            this.loadDashboard();
        });

        document.getElementById('transaction-form').addEventListener('submit', (e) => this.handleTransactionSubmit(e));
        document.getElementById('trans-price').addEventListener('input', () => this.calculateAmount());
        document.getElementById('trans-quantity').addEventListener('input', () => this.calculateAmount());

        document.getElementById('ledger-form').addEventListener('submit', (e) => this.handleLedgerSubmit(e));
        document.getElementById('account-form').addEventListener('submit', (e) => this.handleAccountSubmit(e));
    }

    showPage(pageId) {
        document.querySelectorAll('.page').forEach(page => page.classList.remove('active'));
        document.getElementById(pageId).classList.add('active');
    }

    navigateTo(pageName) {
        document.querySelectorAll('.nav-item').forEach(item => {
            item.classList.toggle('active', item.dataset.page === pageName);
        });

        document.querySelectorAll('.view').forEach(view => view.classList.remove('active'));
        const view = document.getElementById(`${pageName}-view`);
        if (view) {
            view.classList.add('active');
        }

        const titles = {
            'dashboard': '仪表盘',
            'positions': '持仓管理',
            'transactions': '交易记录',
            'funds': '资金明细',
            'add-transaction': '添加交易',
            'analysis': '收益分析',
            'settings': '设置'
        };
        document.getElementById('current-page-title').textContent = titles[pageName] || '仪表盘';

        switch(pageName) {
            case 'dashboard':
                this.loadDashboard();
                break;
            case 'positions':
                this.loadPositions();
                break;
            case 'transactions':
                this.transactionsPage = 1;
                this.loadTransactions();
                break;
            case 'funds':
                this.loadFundTransactions();
                break;
            case 'settings':
                this.loadLedgersAndAccounts();
                break;
        }
    }

    async checkAuth() {
        const token = localStorage.getItem('auth_token');
        const userData = localStorage.getItem('user_data');
        if (token && userData) {
            this.user = JSON.parse(userData);
            this.showMainPage();
        } else {
            this.showPage('login-page');
        }
    }

    async handleLogin(e) {
        e.preventDefault();
        const username = document.getElementById('username').value;
        const password = document.getElementById('password').value;
        const errorEl = document.getElementById('login-error');

        try {
            const response = await fetch(`${this.apiBase}/auth/login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password })
            });

            const data = await response.json();

            if (response.ok && data.success) {
                this.user = data;
                localStorage.setItem('auth_token', 'logged_in');
                localStorage.setItem('user_data', JSON.stringify(data));
                this.showMainPage();
                this.showToast('登录成功', 'success');
            } else {
                errorEl.textContent = data.error || '登录失败';
            }
        } catch (error) {
            errorEl.textContent = '网络错误，请重试';
            console.error('Login error:', error);
        }
    }

    async handleRegister(e) {
        e.preventDefault();
        const email = document.getElementById('reg-email').value;
        const username = document.getElementById('reg-username').value;
        const password = document.getElementById('reg-password').value;
        const passwordConfirm = document.getElementById('reg-password-confirm').value;
        const passwordHint = document.getElementById('reg-password-hint').value;
        const errorEl = document.getElementById('register-error');
        const successEl = document.getElementById('register-success');

        if (password !== passwordConfirm) {
            errorEl.textContent = '两次输入的密码不一致';
            return;
        }

        try {
            const response = await fetch(`${this.apiBase}/auth/register`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    email,
                    username,
                    password,
                    password_repeat: passwordConfirm,
                    password_hint: passwordHint
                })
            });

            const data = await response.json();

            if (response.ok && data.success) {
                successEl.textContent = '注册成功，请登录';
                errorEl.textContent = '';
                setTimeout(() => {
                    this.showPage('login-page');
                }, 1500);
            } else {
                errorEl.textContent = data.error || '注册失败';
            }
        } catch (error) {
            errorEl.textContent = '网络错误，请重试';
            console.error('Register error:', error);
        }
    }

    handleLogout() {
        localStorage.removeItem('auth_token');
        localStorage.removeItem('user_data');
        this.user = null;
        this.showPage('login-page');
        this.showToast('已退出登录', 'success');
    }

    showMainPage() {
        this.showPage('main-page');
        document.getElementById('user-name').textContent = this.user.name || this.user.username;
        this.loadLedgers();
    }

    toggleSidebar() {
        document.getElementById('sidebar').classList.toggle('collapsed');
    }

    async loadLedgers() {
        try {
            const response = await fetch(`${this.apiBase}/ledgers?username=${this.user.username}`);
            const data = await response.json();

            if (response.ok) {
                this.ledgers = data.ledgers || [];
                this.updateLedgerSelect();
                if (this.ledgers.length > 0) {
                    this.currentLedgerId = this.ledgers[0].id;
                    document.getElementById('ledger-select').value = this.currentLedgerId;
                    this.loadAccounts();
                    this.loadDashboard();
                }
            }
        } catch (error) {
            console.error('Load ledgers error:', error);
            this.showToast('加载账本失败', 'error');
        }
    }

    updateLedgerSelect() {
        const select = document.getElementById('ledger-select');
        const select2 = document.getElementById('account-ledger-select');
        select.innerHTML = '<option value="">选择账本</option>';
        select2.innerHTML = '<option value="">选择账本</option>';

        this.ledgers.forEach(ledger => {
            select.innerHTML += `<option value="${ledger.id}">${ledger.name}</option>`;
            select2.innerHTML += `<option value="${ledger.id}">${ledger.name}</option>`;
        });
    }

    async loadAccounts() {
        if (!this.currentLedgerId) {
            this.accounts = [];
            this.updateAccountSelect();
            return;
        }

        try {
            const response = await fetch(`${this.apiBase}/accounts?ledger_id=${this.currentLedgerId}`);
            const data = await response.json();

            if (response.ok) {
                this.accounts = data.accounts || [];
                this.updateAccountSelect();
            }
        } catch (error) {
            console.error('Load accounts error:', error);
        }
    }

    updateAccountSelect() {
        const select = document.getElementById('account-select');
        select.innerHTML = '<option value="">全部账户</option>';

        this.accounts.forEach(account => {
            select.innerHTML += `<option value="${account.id}">${account.name} (${account.currency})</option>`;
        });
    }

    async loadDashboard() {
        if (!this.currentLedgerId) {
            this.resetDashboard();
            return;
        }

        try {
            const params = new URLSearchParams({
                ledger_id: this.currentLedgerId
            });
            if (this.currentAccountId) {
                params.append('account_id', this.currentAccountId);
            }

            const response = await fetch(`${this.apiBase}/portfolio/stats?${params}`);
            const data = await response.json();

            if (response.ok) {
                this.updateDashboardStats(data.stats);
                this.loadPositions();
                this.loadRecentTransactions();
            }
        } catch (error) {
            console.error('Load dashboard error:', error);
            this.showToast('加载数据失败', 'error');
        }
    }

    resetDashboard() {
        document.getElementById('total-cost').textContent = '¥0.00';
        document.getElementById('total-value').textContent = '¥0.00';
        document.getElementById('total-profit').textContent = '¥0.00';
        document.getElementById('profit-rate').textContent = '0.00%';
        document.getElementById('position-count').textContent = '0';
    }

    updateDashboardStats(stats) {
        const formatCurrency = (value) => {
            if (value === null || value === undefined) return '¥0.00';
            return '¥' + parseFloat(value).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
        };

        document.getElementById('total-cost').textContent = formatCurrency(stats.total_cost_cny);
        document.getElementById('total-value').textContent = formatCurrency(stats.total_value_cny);
        document.getElementById('total-profit').textContent = formatCurrency(stats.total_profit_cny);
        document.getElementById('position-count').textContent = stats.position_count || 0;

        const profitRate = parseFloat(stats.profit_rate) || 0;
        document.getElementById('profit-rate').textContent = profitRate.toFixed(2) + '%';
        document.getElementById('profit-rate').className = 'stat-rate ' + (profitRate >= 0 ? 'profit-positive' : 'profit-negative');

        const profitIcon = document.getElementById('profit-icon');
        profitIcon.className = 'stat-icon ' + (profitRate >= 0 ? 'green' : 'red');
    }

    async loadPositions() {
        if (!this.currentLedgerId) {
            document.getElementById('positions-list').innerHTML = '<tr><td colspan="8" class="empty-message">暂无持仓数据</td></tr>';
            return;
        }

        try {
            const params = new URLSearchParams({ ledger_id: this.currentLedgerId });
            if (this.currentAccountId) {
                params.append('account_id', this.currentAccountId);
            }

            const response = await fetch(`${this.apiBase}/positions?${params}`);
            const data = await response.json();

            if (response.ok) {
                this.updatePositionsTable(data.positions || []);
                this.updateCharts(data.positions || []);
            }
        } catch (error) {
            console.error('Load positions error:', error);
        }
    }

    updatePositionsTable(positions) {
        const tbody = document.getElementById('positions-list');

        if (positions.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" class="empty-message">暂无持仓数据</td></tr>';
            return;
        }

        const formatCurrency = (value) => {
            if (value === null || value === undefined) return '¥0.00';
            return '¥' + parseFloat(value).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
        };

        tbody.innerHTML = positions.map(pos => {
            const profit = (pos.market_value_cny || 0) - (pos.cost_cny || 0);
            const profitRate = pos.cost_cny ? ((profit / pos.cost_cny) * 100) : 0;

            return `
                <tr>
                    <td>${pos.code || '-'}</td>
                    <td>${pos.name || '-'}</td>
                    <td>${pos.quantity || 0}</td>
                    <td>${formatCurrency(pos.avg_cost)}</td>
                    <td>${formatCurrency(pos.current_price)}</td>
                    <td>${formatCurrency(pos.market_value_cny)}</td>
                    <td class="${profit >= 0 ? 'profit-positive' : 'profit-negative'}">${formatCurrency(profit)}</td>
                    <td class="${profitRate >= 0 ? 'profit-positive' : 'profit-negative'}">${profitRate.toFixed(2)}%</td>
                </tr>
            `;
        }).join('');
    }

    updateCharts(positions) {
        const allocationChart = document.getElementById('allocation-chart');
        const profitChart = document.getElementById('profit-chart');

        if (positions.length === 0) {
            allocationChart.innerHTML = '<div class="empty-state"><span class="material-icons">pie_chart</span><p>暂无持仓数据</p></div>';
            profitChart.innerHTML = '<div class="empty-state"><span class="material-icons">bar_chart</span><p>暂无持仓数据</p></div>';
            return;
        }

        const labels = positions.map(p => p.name);
        const values = positions.map(p => p.market_value_cny || 0);
        const profits = positions.map(p => (p.market_value_cny || 0) - (p.cost_cny || 0));

        this.drawPieChart(allocationChart, labels, values, '市值 (CNY)');
        this.drawBarChart(profitChart, labels, profits, '收益 (CNY)');
    }

    drawPieChart(container, labels, values, title) {
        const canvas = document.createElement('canvas');
        canvas.width = container.clientWidth;
        canvas.height = container.clientHeight - 20;
        container.innerHTML = '';
        container.appendChild(canvas);

        const ctx = canvas.getContext('2d');
        const total = values.reduce((sum, v) => sum + v, 0);
        if (total === 0) return;

        const centerX = canvas.width / 2;
        const centerY = canvas.height / 2;
        const radius = Math.min(centerX, centerY) - 40;

        const colors = [
            '#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6',
            '#ec4899', '#06b6d4', '#84cc16', '#f97316', '#6366f1'
        ];

        let startAngle = -Math.PI / 2;

        labels.forEach((label, i) => {
            const sliceAngle = (values[i] / total) * 2 * Math.PI;
            const endAngle = startAngle + sliceAngle;

            ctx.beginPath();
            ctx.moveTo(centerX, centerY);
            ctx.arc(centerX, centerY, radius, startAngle, endAngle);
            ctx.closePath();
            ctx.fillStyle = colors[i % colors.length];
            ctx.fill();

            ctx.beginPath();
            ctx.moveTo(centerX, centerY);
            ctx.arc(centerX, centerY, radius * 0.6, 0, 2 * Math.PI);
            ctx.fillStyle = '#ffffff';
            ctx.fill();

            startAngle = endAngle;
        });

        ctx.fillStyle = '#1e293b';
        ctx.font = '14px Inter, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(title, centerX, centerY);
    }

    drawBarChart(container, labels, values, title) {
        const canvas = document.createElement('canvas');
        canvas.width = container.clientWidth;
        canvas.height = container.clientHeight - 20;
        container.innerHTML = '';
        container.appendChild(canvas);

        const ctx = canvas.getContext('2d');

        const padding = { top: 20, right: 20, bottom: 60, left: 80 };
        const chartWidth = canvas.width - padding.left - padding.right;
        const chartHeight = canvas.height - padding.top - padding.bottom;

        if (labels.length === 0) return;

        const maxValue = Math.max(...values.map(Math.abs), 1);
        const barWidth = chartWidth / labels.length * 0.7;
        const barGap = chartWidth / labels.length * 0.3;

        const zeroY = padding.top + chartHeight / 2;

        labels.forEach((label, i) => {
            const value = values[i];
            const normalizedHeight = (Math.abs(value) / maxValue) * (chartHeight / 2 - 10);
            const barX = padding.left + i * (barWidth + barGap) + barGap / 2;
            const barY = value >= 0 ? zeroY - normalizedHeight : zeroY;
            const height = normalizedHeight;

            ctx.fillStyle = value >= 0 ? '#10b981' : '#ef4444';
            ctx.fillRect(barX, barY, barWidth, height);

            ctx.fillStyle = '#64748b';
            ctx.font = '11px Inter, sans-serif';
            ctx.textAlign = 'center';
            ctx.save();
            ctx.translate(barX + barWidth / 2, canvas.height - padding.bottom + 15);
            ctx.rotate(-Math.PI / 4);
            ctx.fillText(label, 0, 0);
            ctx.restore();
        });

        ctx.strokeStyle = '#e2e8f0';
        ctx.beginPath();
        ctx.moveTo(padding.left, zeroY);
        ctx.lineTo(canvas.width - padding.right, zeroY);
        ctx.stroke();
    }

    async loadRecentTransactions() {
        try {
            const params = new URLSearchParams({
                ledger_id: this.currentLedgerId,
                limit: 5
            });
            if (this.currentAccountId) {
                params.append('account_id', this.currentAccountId);
            }

            const response = await fetch(`${this.apiBase}/transactions?${params}`);
            const data = await response.json();

            if (response.ok) {
                this.updateRecentTransactions(data.transactions || []);
            }
        } catch (error) {
            console.error('Load recent transactions error:', error);
        }
    }

    updateRecentTransactions(transactions) {
        const tbody = document.getElementById('recent-transactions');

        if (transactions.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-message">暂无交易记录</td></tr>';
            return;
        }

        const formatCurrency = (value) => {
            if (value === null || value === undefined) return '¥0.00';
            return '¥' + parseFloat(value).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
        };

        tbody.innerHTML = transactions.map(trans => `
            <tr>
                <td>${trans.date || '-'}</td>
                <td>${trans.type || '-'}</td>
                <td>${trans.code || '-'}</td>
                <td>${trans.name || '-'}</td>
                <td>${formatCurrency(trans.price)}</td>
                <td>${trans.quantity || 0}</td>
                <td>${formatCurrency(trans.amount)}</td>
            </tr>
        `).join('');
    }

    async loadTransactions() {
        if (!this.currentLedgerId) {
            document.getElementById('transactions-list').innerHTML = '<tr><td colspan="9" class="empty-message">请先选择账本</td></tr>';
            return;
        }

        try {
            const type = document.getElementById('trans-type-filter').value;
            const startDate = document.getElementById('trans-start-date').value;
            const endDate = document.getElementById('trans-end-date').value;

            const params = new URLSearchParams({
                ledger_id: this.currentLedgerId,
                limit: this.transactionsPerPage,
                offset: (this.transactionsPage - 1) * this.transactionsPerPage
            });

            if (this.currentAccountId) {
                params.append('account_id', this.currentAccountId);
            }
            if (type) {
                params.append('type', type);
            }
            if (startDate) {
                params.append('start_date', startDate);
            }
            if (endDate) {
                params.append('end_date', endDate);
            }

            const response = await fetch(`${this.apiBase}/transactions?${params}`);
            const data = await response.json();

            if (response.ok) {
                this.updateTransactionsTable(data.transactions || []);
                this.updateTransactionsPagination(data.total || 0);
            }
        } catch (error) {
            console.error('Load transactions error:', error);
            this.showToast('加载交易记录失败', 'error');
        }
    }

    updateTransactionsTable(transactions) {
        const tbody = document.getElementById('transactions-list');

        if (transactions.length === 0) {
            tbody.innerHTML = '<tr><td colspan="9" class="empty-message">暂无交易记录</td></tr>';
            return;
        }

        const formatCurrency = (value) => {
            if (value === null || value === undefined) return '¥0.00';
            return '¥' + parseFloat(value).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
        };

        tbody.innerHTML = transactions.map(trans => `
            <tr>
                <td>${trans.date || '-'}</td>
                <td><span class="badge badge-${trans.type === '买入' ? 'success' : trans.type === '卖出' ? 'danger' : 'info'}">${trans.type || '-'}</span></td>
                <td>${trans.code || '-'}</td>
                <td>${trans.name || '-'}</td>
                <td>${formatCurrency(trans.price)}</td>
                <td>${trans.quantity || 0}</td>
                <td>${formatCurrency(trans.amount)}</td>
                <td>${formatCurrency(trans.fee)}</td>
                <td class="actions">
                    <button class="btn-icon" onclick="app.deleteTransaction(${trans.id})" title="删除">
                        <span class="material-icons">delete</span>
                    </button>
                </td>
            </tr>
        `).join('');
    }

    updateTransactionsPagination(total) {
        const totalPages = Math.ceil(total / this.transactionsPerPage);
        const pagination = document.getElementById('transactions-pagination');

        if (totalPages <= 1) {
            pagination.innerHTML = '';
            return;
        }

        let html = `
            <button ${this.transactionsPage === 1 ? 'disabled' : ''} onclick="app.goToTransactionsPage(${this.transactionsPage - 1})">上一页</button>
        `;

        for (let i = 1; i <= totalPages; i++) {
            if (i === 1 || i === totalPages || (i >= this.transactionsPage - 1 && i <= this.transactionsPage + 1)) {
                html += `<button class="${i === this.transactionsPage ? 'active' : ''}" onclick="app.goToTransactionsPage(${i})">${i}</button>`;
            } else if (i === this.transactionsPage - 2 || i === this.transactionsPage + 2) {
                html += `<button disabled>...</button>`;
            }
        }

        html += `
            <button ${this.transactionsPage === totalPages ? 'disabled' : ''} onclick="app.goToTransactionsPage(${this.transactionsPage + 1})">下一页</button>
        `;

        pagination.innerHTML = html;
    }

    goToTransactionsPage(page) {
        this.transactionsPage = page;
        this.loadTransactions();
    }

    async deleteTransaction(id) {
        if (!confirm('确定要删除这条交易记录吗？')) return;

        try {
            const response = await fetch(`${this.apiBase}/transactions/${id}`, {
                method: 'DELETE'
            });

            const data = await response.json();

            if (response.ok && data.success) {
                this.showToast('删除成功', 'success');
                this.loadTransactions();
                this.loadDashboard();
            } else {
                this.showToast(data.error || '删除失败', 'error');
            }
        } catch (error) {
            console.error('Delete transaction error:', error);
            this.showToast('删除失败', 'error');
        }
    }

    async loadFundTransactions() {
        if (!this.currentLedgerId) {
            document.getElementById('funds-list').innerHTML = '<tr><td colspan="6" class="empty-message">请先选择账本</td></tr>';
            return;
        }

        try {
            const type = document.getElementById('fund-type-filter').value;

            const params = new URLSearchParams({
                ledger_id: this.currentLedgerId,
                limit: 50
            });

            if (this.currentAccountId) {
                params.append('account_id', this.currentAccountId);
            }
            if (type) {
                params.append('type', type);
            }

            const response = await fetch(`${this.apiBase}/fund-transactions?${params}`);
            const data = await response.json();

            if (response.ok) {
                this.updateFundsTable(data.fund_transactions || []);
            }
        } catch (error) {
            console.error('Load fund transactions error:', error);
            this.showToast('加载资金明细失败', 'error');
        }
    }

    updateFundsTable(funds) {
        const tbody = document.getElementById('funds-list');

        if (funds.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="empty-message">暂无资金明细</td></tr>';
            return;
        }

        const formatCurrency = (value, currency = 'CNY') => {
            if (value === null || value === undefined) return '¥0.00';
            return currency + ' ' + parseFloat(value).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
        };

        tbody.innerHTML = funds.map(fund => `
            <tr>
                <td>${fund.date || '-'}</td>
                <td>${fund.type || '-'}</td>
                <td>${formatCurrency(fund.amount, fund.currency)}</td>
                <td>${fund.currency || '-'}</td>
                <td>¥${(fund.amount_cny || 0).toFixed(2)}</td>
                <td>${fund.description || '-'}</td>
            </tr>
        `).join('');
    }

    showAddTransactionModal() {
        if (!this.currentLedgerId) {
            this.showToast('请先选择账本', 'warning');
            return;
        }

        document.getElementById('trans-date').value = new Date().toISOString().split('T')[0];
        document.getElementById('trans-ledger').value = this.currentLedgerId;

        this.loadCategories();
        this.navigateTo('add-transaction');
    }

    async loadCategories() {
        try {
            const response = await fetch(`${this.apiBase}/categories`);
            const data = await response.json();

            if (response.ok) {
                const select = document.getElementById('trans-category');
                select.innerHTML = '<option value="">选择类别</option>';
                (data.categories || []).forEach(cat => {
                    select.innerHTML += `<option value="${cat.name}">${cat.name}</option>`;
                });
            }
        } catch (error) {
            console.error('Load categories error:', error);
        }
    }

    calculateAmount() {
        const price = parseFloat(document.getElementById('trans-price').value) || 0;
        const quantity = parseFloat(document.getElementById('trans-quantity').value) || 0;
        document.getElementById('trans-amount').value = (price * quantity).toFixed(2);
    }

    async handleTransactionSubmit(e) {
        e.preventDefault();

        const formData = new FormData(e.target);
        const transaction = {
            ledger_id: parseInt(formData.get('ledger_id')),
            account_id: parseInt(formData.get('account_id')),
            type: formData.get('type'),
            date: formData.get('date'),
            code: formData.get('code'),
            name: formData.get('name'),
            price: parseFloat(formData.get('price')),
            quantity: parseFloat(formData.get('quantity')),
            amount: parseFloat(formData.get('amount')),
            fee: parseFloat(formData.get('fee')) || 0,
            category: formData.get('category') || null,
            notes: formData.get('notes') || ''
        };

        try {
            const response = await fetch(`${this.apiBase}/transactions`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(transaction)
            });

            const data = await response.json();

            if (response.ok && data.success) {
                this.showToast('交易记录添加成功', 'success');
                e.target.reset();
                this.loadDashboard();
                this.navigateTo('transactions');
            } else {
                this.showToast(data.error || '添加失败', 'error');
            }
        } catch (error) {
            console.error('Submit transaction error:', error);
            this.showToast('添加失败', 'error');
        }
    }

    showAddFundModal() {
        this.showModal('添加资金明细', `
            <form id="fund-form">
                <div class="form-group">
                    <label>账本</label>
                    <select name="ledger_id" required>
                        <option value="">选择账本</option>
                        ${this.ledgers.map(l => `<option value="${l.id}">${l.name}</option>`).join('')}
                    </select>
                </div>
                <div class="form-group">
                    <label>账户</label>
                    <select name="account_id" required>
                        <option value="">选择账户</option>
                        ${this.accounts.map(a => `<option value="${a.id}">${a.name}</option>`).join('')}
                    </select>
                </div>
                <div class="form-group">
                    <label>类型</label>
                    <select name="type" required>
                        <option value="">选择类型</option>
                        <option value="本金投入">本金投入</option>
                        <option value="本金撤出">本金撤出</option>
                        <option value="收入">收入</option>
                        <option value="支出">支出</option>
                        <option value="内转">内转</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>日期</label>
                    <input type="date" name="date" required value="${new Date().toISOString().split('T')[0]}">
                </div>
                <div class="form-group">
                    <label>金额</label>
                    <input type="number" name="amount" step="0.01" required placeholder="0.00">
                </div>
                <div class="form-group">
                    <label>币种</label>
                    <select name="currency">
                        <option value="CNY">CNY</option>
                        <option value="USD">USD</option>
                        <option value="HKD">HKD</option>
                        <option value="EUR">EUR</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>描述</label>
                    <textarea name="description" rows="3" placeholder="添加描述..."></textarea>
                </div>
                <div class="form-actions">
                    <button type="submit" class="btn btn-primary">保存</button>
                    <button type="button" class="btn btn-outline" onclick="app.closeModal()">取消</button>
                </div>
            </form>
        `);

        document.getElementById('fund-form').addEventListener('submit', (e) => this.handleFundSubmit(e));
    }

    async handleFundSubmit(e) {
        e.preventDefault();

        const formData = new FormData(e.target);
        const fund = {
            ledger_id: parseInt(formData.get('ledger_id')),
            account_id: parseInt(formData.get('account_id')),
            type: formData.get('type'),
            date: formData.get('date'),
            amount: parseFloat(formData.get('amount')),
            currency: formData.get('currency'),
            description: formData.get('description') || ''
        };

        try {
            const response = await fetch(`${this.apiBase}/fund-transactions`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(fund)
            });

            const data = await response.json();

            if (response.ok && data.success) {
                this.showToast('资金明细添加成功', 'success');
                this.closeModal();
                this.loadFundTransactions();
            } else {
                this.showToast(data.error || '添加失败', 'error');
            }
        } catch (error) {
            console.error('Submit fund error:', error);
            this.showToast('添加失败', 'error');
        }
    }

    async loadLedgersAndAccounts() {
        await this.loadLedgers();
        this.renderLedgersList();
        this.renderAccountsList();
    }

    renderLedgersList() {
        const container = document.getElementById('ledgers-list');

        if (this.ledgers.length === 0) {
            container.innerHTML = '<p class="empty-message">暂无账本</p>';
            return;
        }

        container.innerHTML = this.ledgers.map(ledger => `
            <div class="item-card">
                <div class="item-info">
                    <span class="item-name">${ledger.name}</span>
                    <span class="item-desc">${ledger.description || '无描述'} | ${ledger.cost_method}</span>
                </div>
                <div class="item-actions">
                    <button class="btn-icon" onclick="app.deleteLedger(${ledger.id})" title="删除">
                        <span class="material-icons">delete</span>
                    </button>
                </div>
            </div>
        `).join('');
    }

    async handleLedgerSubmit(e) {
        e.preventDefault();

        const name = document.getElementById('new-ledger-name').value;
        const description = document.getElementById('new-ledger-desc').value;

        if (!name) {
            this.showToast('请输入账本名称', 'warning');
            return;
        }

        try {
            const response = await fetch(`${this.apiBase}/ledgers`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    username: this.user.username,
                    name,
                    description,
                    cost_method: 'FIFO'
                })
            });

            const data = await response.json();

            if (response.ok && data.success) {
                this.showToast('账本创建成功', 'success');
                document.getElementById('new-ledger-name').value = '';
                document.getElementById('new-ledger-desc').value = '';
                this.loadLedgersAndAccounts();
            } else {
                this.showToast(data.error || '创建失败', 'error');
            }
        } catch (error) {
            console.error('Create ledger error:', error);
            this.showToast('创建失败', 'error');
        }
    }

    async deleteLedger(id) {
        if (!confirm('确定要删除这个账本吗？所有相关数据将被删除。')) return;

        try {
            const response = await fetch(`${this.apiBase}/ledgers/${id}?username=${this.user.username}`, {
                method: 'DELETE'
            });

            const data = await response.json();

            if (response.ok && data.success) {
                this.showToast('账本删除成功', 'success');
                this.loadLedgersAndAccounts();
            } else {
                this.showToast(data.error || '删除失败', 'error');
            }
        } catch (error) {
            console.error('Delete ledger error:', error);
            this.showToast('删除失败', 'error');
        }
    }

    renderAccountsList() {
        const container = document.getElementById('accounts-list');

        if (this.accounts.length === 0) {
            container.innerHTML = '<p class="empty-message">暂无账户</p>';
            return;
        }

        container.innerHTML = this.accounts.map(account => `
            <div class="item-card">
                <div class="item-info">
                    <span class="item-name">${account.name}</span>
                    <span class="item-desc">${account.type} | ${account.currency}</span>
                </div>
                <div class="item-actions">
                    <button class="btn-icon" onclick="app.deleteAccount(${account.id})" title="删除">
                        <span class="material-icons">delete</span>
                    </button>
                </div>
            </div>
        `).join('');
    }

    async handleAccountSubmit(e) {
        e.preventDefault();

        const ledgerId = document.getElementById('account-ledger-select').value;
        const name = document.getElementById('new-account-name').value;
        const type = document.getElementById('new-account-type').value;
        const currency = document.getElementById('new-account-currency').value;

        if (!ledgerId || !name) {
            this.showToast('请填写完整信息', 'warning');
            return;
        }

        try {
            const response = await fetch(`${this.apiBase}/accounts`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    ledger_id: parseInt(ledgerId),
                    name,
                    type,
                    currency
                })
            });

            const data = await response.json();

            if (response.ok && data.success) {
                this.showToast('账户创建成功', 'success');
                document.getElementById('new-account-name').value = '';
                this.loadAccounts();
                this.loadLedgersAndAccounts();
            } else {
                this.showToast(data.error || '创建失败', 'error');
            }
        } catch (error) {
            console.error('Create account error:', error);
            this.showToast('创建失败', 'error');
        }
    }

    async deleteAccount(id) {
        if (!confirm('确定要删除这个账户吗？所有相关数据将被删除。')) return;

        try {
            const response = await fetch(`${this.apiBase}/accounts/${id}`, {
                method: 'DELETE'
            });

            const data = await response.json();

            if (response.ok && data.success) {
                this.showToast('账户删除成功', 'success');
                this.loadAccounts();
                this.loadLedgersAndAccounts();
            } else {
                this.showToast(data.error || '删除失败', 'error');
            }
        } catch (error) {
            console.error('Delete account error:', error);
            this.showToast('删除失败', 'error');
        }
    }

    showModal(title, content) {
        document.getElementById('modal-title').textContent = title;
        document.getElementById('modal-body').innerHTML = content;
        document.getElementById('modal').classList.add('active');
    }

    closeModal() {
        document.getElementById('modal').classList.remove('active');
    }

    showToast(message, type = 'info') {
        const toast = document.getElementById('toast');
        toast.textContent = message;
        toast.className = 'toast show ' + type;

        setTimeout(() => {
            toast.classList.remove('show');
        }, 3000);
    }
}

const app = new InvestmentTracker();
