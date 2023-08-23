-- Initialize the database.
-- Drop any existing data and create empty tables.

DROP TABLE IF EXISTS user;
DROP TABLE IF EXISTS holdings;
DROP TABLE IF EXISTS history;

CREATE TABLE user (
  userid INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  password TEXT NOT NULL,
  account_balance REAL DEFAULT 0
);

-- CREATE TABLE adm (
--   userid INTEGER PRIMARY KEY DEFAULT 0,
--   username TEXT UNIQUE NOT NULL DEFAULT 'adm',
--   password TEXT NOT NULL DEFAULT '123',
-- );

-- CREATE TABLE account (
--   accountid INTEGER PRIMARY KEY AUTOINCREMENT,
--   account_balance FLOAT NOT NULL,
--   FOREIGN KEY (userid)
-- );

CREATE TABLE holdings (
  holdingid INTEGER PRIMARY KEY AUTOINCREMENT,
  stockid INTEGER NOT NULL,
  -- created_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  price REAL NOT NULL,
  new_price REAL NOT NULL,
  shares INT NOT NULL,
  u_id INT NOT NULL,
  worth REAL NOT NULL,
  FOREIGN KEY (u_id) REFERENCES user (userid)
);

-- CREATE TABLE stock (
--   symbol CHAR(10) NOT NULL,
--   date TIMESTAMP NOT NULL,
--   created TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
--   close_price FLOAT NOT NULL,
-- );

CREATE TABLE history (
  holdingid INTEGER PRIMARY KEY AUTOINCREMENT,
  stockid INTEGER NOT NULL,
  created_time TIMESTAMP NOT NULL,
  price FLOAT NOT NULL,
  shares INT NOT NULL,
  u_id INT NOT NULL,
  worth FLOAT NOT NULL,
  FOREIGN KEY (u_id) REFERENCES user (userid)
);
