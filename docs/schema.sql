-- GP 自选股看盘系统 数据库表结构
-- 由 backend/init_db.py (SQLAlchemy create_all) 自动生成，此处为导出快照供部署审阅
-- 生成时间: 2026-08-07

CREATE TABLE adjust_factor (
	id INTEGER NOT NULL, 
	stock_code VARCHAR(20) NOT NULL, 
	trade_date VARCHAR(10) NOT NULL, 
	factor FLOAT NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE alerts (
	id INTEGER NOT NULL, 
	stock_code VARCHAR(20) NOT NULL, 
	stock_name VARCHAR(50) NOT NULL, 
	target_price FLOAT NOT NULL, 
	direction VARCHAR(10) NOT NULL, 
	triggered BOOLEAN NOT NULL, 
	triggered_at DATETIME, 
	created_at DATETIME NOT NULL, alert_type VARCHAR(20) DEFAULT 'price', pct_threshold FLOAT DEFAULT 0, volume_ratio FLOAT DEFAULT 0, volume_days INTEGER DEFAULT 5, 
	PRIMARY KEY (id)
);

CREATE TABLE annotations (
	id VARCHAR(36) NOT NULL, 
	stock_code VARCHAR(20) NOT NULL, 
	trade_date VARCHAR(10) NOT NULL, 
	type VARCHAR(20) NOT NULL, 
	content TEXT NOT NULL, 
	position VARCHAR(10), 
	idempotency_key VARCHAR(64), 
	created_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
	updated_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (idempotency_key)
);

CREATE TABLE drawings (
	id INTEGER NOT NULL, 
	stock_code VARCHAR(20) NOT NULL, 
	period VARCHAR(10) NOT NULL, 
	type VARCHAR(30) NOT NULL, 
	points TEXT NOT NULL, 
	style TEXT, 
	text_content TEXT, 
	visible BOOLEAN, 
	idempotency_key VARCHAR(64), 
	created_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
	updated_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (idempotency_key)
);

CREATE TABLE groups (
	id INTEGER NOT NULL, 
	name VARCHAR(50) NOT NULL, 
	sort_order INTEGER, 
	created_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
	updated_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (name)
);

CREATE TABLE journals (
	id INTEGER NOT NULL, 
	trade_date DATE NOT NULL, 
	operations TEXT NOT NULL, 
	market_obs TEXT NOT NULL, 
	"plan" TEXT NOT NULL, 
	mood VARCHAR(20) NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_journal_trade_date UNIQUE (trade_date), 
	UNIQUE (trade_date)
);

CREATE TABLE kline_adjusted (
	id INTEGER NOT NULL, 
	stock_code VARCHAR(20) NOT NULL, 
	trade_date VARCHAR(10) NOT NULL, 
	adj_type VARCHAR(4) NOT NULL, 
	open FLOAT NOT NULL, 
	high FLOAT NOT NULL, 
	low FLOAT NOT NULL, 
	close FLOAT NOT NULL, 
	volume BIGINT NOT NULL, 
	amount FLOAT, 
	PRIMARY KEY (id)
);

CREATE TABLE kline_data (
	id INTEGER NOT NULL, 
	stock_code VARCHAR(20) NOT NULL, 
	trade_date VARCHAR(10) NOT NULL, 
	open FLOAT NOT NULL, 
	high FLOAT NOT NULL, 
	low FLOAT NOT NULL, 
	close FLOAT NOT NULL, 
	volume BIGINT NOT NULL, 
	amount FLOAT, 
	PRIMARY KEY (id)
);

CREATE TABLE news_digests (id INTEGER NOT NULL, sector VARCHAR(50) NOT NULL, date VARCHAR(20) NOT NULL, points TEXT, created_at DATETIME, updated_at DATETIME, PRIMARY KEY (id), UNIQUE (sector, date));

CREATE TABLE news_items (
	id INTEGER NOT NULL, 
	sector VARCHAR(50) NOT NULL, 
	title VARCHAR(500) NOT NULL, 
	link VARCHAR(1000), 
	date VARCHAR(100), 
	summary TEXT, 
	source VARCHAR(200), 
	digest TEXT, 
	fetched_at DATETIME, title_zh VARCHAR(500) DEFAULT '', published_at VARCHAR(20) DEFAULT '', content TEXT DEFAULT '', content_zh TEXT DEFAULT '', 
	PRIMARY KEY (id)
);

CREATE TABLE positions (
	id INTEGER NOT NULL, 
	stock_code VARCHAR(20) NOT NULL, 
	stock_name VARCHAR(50) NOT NULL, 
	cost_price FLOAT NOT NULL, 
	quantity INTEGER NOT NULL, 
	buy_date VARCHAR(10) NOT NULL, 
	note VARCHAR(500) NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE prediction_records (
	id INTEGER NOT NULL, 
	stock_code VARCHAR(20) NOT NULL, 
	predict_date VARCHAR(10) NOT NULL, 
	model_name VARCHAR(40) NOT NULL, 
	horizon_days INTEGER NOT NULL, 
	trend VARCHAR(20) NOT NULL, 
	confidence FLOAT, 
	price_at_predict FLOAT, 
	evaluated BOOLEAN, 
	eval_date VARCHAR(10), 
	price_at_eval FLOAT, 
	actual_trend VARCHAR(20), 
	is_correct BOOLEAN, 
	PRIMARY KEY (id)
);

CREATE TABLE watchlist (
	id INTEGER NOT NULL, 
	stock_code VARCHAR(20) NOT NULL, 
	stock_name VARCHAR(50) NOT NULL, 
	group_id INTEGER, 
	note TEXT, 
	sort_order INTEGER, 
	created_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
	updated_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (stock_code), 
	FOREIGN KEY(group_id) REFERENCES groups (id) ON DELETE SET NULL
);

CREATE UNIQUE INDEX idx_adjust_code_date ON adjust_factor (stock_code, trade_date);

CREATE INDEX idx_annotation_code_date ON annotations (stock_code, trade_date);

CREATE INDEX idx_drawing_code_period ON drawings (stock_code, period);

CREATE UNIQUE INDEX idx_kadj_code_date_type ON kline_adjusted (stock_code, trade_date, adj_type);

CREATE UNIQUE INDEX idx_kline_code_date ON kline_data (stock_code, trade_date);

CREATE INDEX idx_news_published ON news_items (published_at);

CREATE INDEX idx_news_sector_date ON news_items (sector, published_at);

CREATE INDEX idx_news_sector_fetched ON news_items (sector, fetched_at);

CREATE INDEX idx_pred_code_date_model ON prediction_records (stock_code, predict_date, model_name);

CREATE INDEX idx_watchlist_group ON watchlist (group_id);

CREATE INDEX ix_adjust_factor_stock_code ON adjust_factor (stock_code);

CREATE INDEX ix_alerts_stock_code ON alerts (stock_code);

CREATE INDEX ix_annotations_stock_code ON annotations (stock_code);

CREATE INDEX ix_drawings_stock_code ON drawings (stock_code);

CREATE INDEX ix_kline_adjusted_stock_code ON kline_adjusted (stock_code);

CREATE INDEX ix_kline_data_stock_code ON kline_data (stock_code);

CREATE INDEX ix_news_items_sector ON news_items (sector);

CREATE INDEX ix_positions_stock_code ON positions (stock_code);

CREATE INDEX ix_prediction_records_stock_code ON prediction_records (stock_code);
