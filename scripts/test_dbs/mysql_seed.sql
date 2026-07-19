CREATE TABLE IF NOT EXISTS orders (
    id INT NOT NULL PRIMARY KEY,
    amount DECIMAL(12, 2) NULL,
    status VARCHAR(32) NULL,
    created_at DATETIME NULL
);

INSERT IGNORE INTO orders (id, amount, status, created_at) VALUES
    (1, 12.50, 'paid', '2026-07-19 10:00:00'),
    (2, 0.00, '', '2026-07-19 11:00:00'),
    (3, NULL, NULL, '2026-07-19 12:00:00');
