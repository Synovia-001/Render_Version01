/*
Create a simple pack-size mapping table so the EPOS module can convert
EPOS sales units -> replenishment order cases.

Populate Units_Per_Case per Dynamics_Code (SKU).
*/
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'CFG')
BEGIN
    EXEC('CREATE SCHEMA CFG');
END
GO

IF OBJECT_ID('CFG.ReplenishmentPack', 'U') IS NULL
BEGIN
    CREATE TABLE CFG.ReplenishmentPack (
        Dynamics_Code     VARCHAR(50)  NOT NULL PRIMARY KEY,
        Units_Per_Case    INT          NOT NULL CONSTRAINT DF_ReplenishmentPack_UnitsPerCase DEFAULT(1),
        Case_Multiple     INT          NULL,   -- optional (e.g., order in multiples of X cases)
        Notes             VARCHAR(255) NULL,
        UpdatedAt         DATETIME2(0) NOT NULL CONSTRAINT DF_ReplenishmentPack_UpdatedAt DEFAULT (SYSUTCDATETIME())
    );
END
GO

/* Example:
INSERT INTO CFG.ReplenishmentPack (Dynamics_Code, Units_Per_Case, Case_Multiple, Notes)
VALUES ('100002065', 12, 1, 'Example pack size');
*/
