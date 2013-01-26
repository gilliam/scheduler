CREATE TABLE hypervisor(
       id INT AUTOINCREMENT PRIMARY KEY,
       host VARCHAR(255)
);

CREATE TABLE proc(
       id INT AUTOINCREMENT PRIMARY KEY,
       app_id INT NOT NULL,
       proc_id VARCHAR(255) NOT NULL,
       name VARCHAR(255) NOT NULL,
       state VARCHAR(64) NOT NULL,
       deploy INT NOT NULL,
       host VARCHAR(255),
       port INT,
       hypervisor_id INT NOT NULL,
       changed_at TIMESTAMP NOT NULL
);

CREATE TABLE app(
       id INT AUTOINCREMENT PRIMARY KEY,
       name VARCHAR(255) NOT NULL,
       deploy_id INT,
       scale VARCHAR(1000),
       repository VARCHAR(255),
       text VARCHAR(1000)
);

CREATE TABLE deploy(
       id INT AUTOINCREMENT PRIMARY KEY,
       build VARCHAR(255),
       image VARCHAR(1024),
       pstable VARCHAR(4096),
       config VARCHAR(60000),
       text VARCHAR(255),
       timestamp TIMESTAMP
);
