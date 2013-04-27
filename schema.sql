CREATE TABLE app(
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       name TEXT NOT NULL,
       text TEXT
);
CREATE UNIQUE INDEX name_idx ON app(name);

CREATE TABLE release(
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       app_id INT NOT NULL,
       version INT NOT NULL,
       text TEXT NOT NULL,
       build TEXT NOT NULL,
       image TEXT NOT NULL,
       pstable TEXT NOT NULL,
       config TEXT NOT NULL,
       scale TEXT,
       timestamp TIMESTAMP
);
CREATE UNIQUE INDEX nam_idx ON release(app_id, version);

CREATE TABLE hypervisor(
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       host TEXT NOT NULL,
       port INT NOT NULL,
       capacity INT NOT NULL,
       options TEXT NOT NULL
);
CREATE UNIQUE INDEX host_idx ON hypervisor(host);

CREATE TABLE proc(
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       app_id INT NOT NULL,
       proc_name TEXT NOT NULL,
       proc_type TEXT NOT NULL,
       desired_state TEXT NOT NULL,
       actual_state TEXT NOT NULL,
       changed_at TIMESTAMP NOT NULL,
       release_id INT NOT NULL,
       hypervisor_id INT NOT NULL,
       port INT,
       cont_entity TEXT
);

