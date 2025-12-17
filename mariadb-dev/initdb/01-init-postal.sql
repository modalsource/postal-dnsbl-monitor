-- Inizializzazione database Postal per DNSBL Monitor
-- Crea schema postal e tabella ip_addresses con colonne necessarie
USE postal;

-- Crea tabella ip_addresses con struttura reale di Postal
CREATE TABLE IF NOT EXISTS `ip_addresses` (
    `id` int NOT NULL AUTO_INCREMENT,
    `ip_pool_id` int DEFAULT NULL,
    `ipv4` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
    `ipv6` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
    `created_at` datetime(6) DEFAULT NULL,
    `updated_at` datetime(6) DEFAULT NULL,
    `hostname` varchar(255) COLLATE utf8mb4_general_ci DEFAULT NULL,
    `priority` int DEFAULT NULL,
    PRIMARY KEY (`id`)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_general_ci;

-- Aggiungi colonne necessarie per DNSBL Monitor
ALTER TABLE
    `ip_addresses`
ADD
    COLUMN IF NOT EXISTS `oldPriority` int DEFAULT NULL
AFTER
    `priority`,
ADD
    COLUMN IF NOT EXISTS `blockingLists` varchar(1024) COLLATE utf8mb4_general_ci DEFAULT ''
AFTER
    `oldPriority`,
ADD
    COLUMN IF NOT EXISTS `lastEvent` varchar(512) COLLATE utf8mb4_general_ci DEFAULT NULL
AFTER
    `blockingLists`;

-- Inserisci dati di test (gli IP reali che hai fornito)
INSERT INTO
    `ip_addresses` (
        `id`,
        `ip_pool_id`,
        `ipv4`,
        `ipv6`,
        `created_at`,
        `updated_at`,
        `hostname`,
        `priority`,
        `oldPriority`,
        `blockingLists`,
        `lastEvent`
    )
VALUES
    (
        1,
        1,
        '195.231.36.228',
        NULL,
        '2025-11-04 10:27:33.795095',
        '2025-12-03 07:41:21.572980',
        'smtp1.example.com',
        100,
        NULL,
        '',
        NULL
    ),
    (
        2,
        1,
        '209.227.233.239',
        NULL,
        '2025-11-04 10:27:54.398781',
        '2025-12-03 13:20:49.346093',
        'smtp2.example.com',
        100,
        NULL,
        '',
        NULL
    ),
    (
        3,
        1,
        '209.227.239.115',
        NULL,
        '2025-12-02 15:22:12.629927',
        '2025-12-12 14:05:03.015996',
        'smtp3.example.com',
        100,
        NULL,
        '',
        NULL
    ),
    (
        4,
        1,
        '209.227.239.184',
        NULL,
        '2025-12-11 20:01:52.928675',
        '2025-12-12 14:05:08.188569',
        'smtp4.example.com',
        100,
        NULL,
        '',
        NULL
    ),
    (
        5,
        1,
        '195.231.36.229',
        NULL,
        '2025-12-11 20:02:19.360630',
        '2025-12-12 14:04:57.599386',
        'smtp5.example.com',
        100,
        NULL,
        '',
        NULL
    ),
    (
        6,
        1,
        '195.231.36.14',
        NULL,
        '2025-12-11 20:02:40.635215',
        '2025-12-12 14:05:18.550437',
        'smtp6.example.com',
        100,
        NULL,
        '',
        NULL
    ),
    (
        7,
        1,
        '209.227.233.135',
        NULL,
        '2025-12-11 20:03:02.262224',
        '2025-12-12 14:05:22.676991',
        'smtp7.example.com',
        100,
        NULL,
        '',
        NULL
    ),
    (
        8,
        1,
        '209.227.233.122',
        NULL,
        '2025-12-11 20:03:29.724607',
        '2025-12-12 14:05:13.283303',
        'smtp8.example.com',
        100,
        NULL,
        '',
        NULL
    ) ON DUPLICATE KEY
UPDATE
    `updated_at` =
VALUES
(`updated_at`),
    `priority` =
VALUES
(`priority`);

-- Verifica dati inseriti
SELECT
    id,
    ipv4,
    hostname,
    priority,
    oldPriority,
    blockingLists,
    lastEvent
FROM
    ip_addresses;