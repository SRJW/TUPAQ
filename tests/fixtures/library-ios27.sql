-- Minimal synthetic MediaLibrary schema/row, based on rustunes 057ee8fc
-- catalogue/sqlite.rs and test_support/catalogue.rs. No user song data.
-- item.media_type is the internal MediaLibrary enum; music is 8, not
-- the public MediaPlayer MPMediaTypeMusic bitmask (1).
PRAGMA user_version=2410000;
CREATE TABLE item(item_pid INTEGER PRIMARY KEY, media_type INTEGER, item_artist_pid INTEGER, album_pid INTEGER);
CREATE TABLE item_extra(item_pid INTEGER PRIMARY KEY,title TEXT,total_time_ms REAL);
CREATE TABLE item_artist(item_artist_pid INTEGER PRIMARY KEY,item_artist TEXT);
CREATE TABLE album(album_pid INTEGER PRIMARY KEY,album TEXT);
INSERT INTO item VALUES(101,8,201,301);
INSERT INTO item_extra VALUES(101,'Canción de catálogo iOS 27',123000);
INSERT INTO item_artist VALUES(201,'Artista sintético');
INSERT INTO album VALUES(301,'Álbum sintético');
