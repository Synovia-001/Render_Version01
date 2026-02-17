/*
  Fusion EPOS module - required view check

  Run this against your EPOS database (set EPOS_DB in Render).
  It will report any missing CUR views expected by the EPOS module.

  NOTE: Adjust database name and schema if your environment differs.
*/

-- Change this if needed:
-- USE [Fusion_EPOS_Production];
-- GO

DECLARE @required TABLE(view_name sysname);
INSERT INTO @required(view_name) VALUES
    ('CUR.vw_StoreWeekly'),
    ('CUR.vw_ProductWeekly'),
    ('CUR.vw_StoreProductWeekly'),
    ('CUR.vw_StoreAnomalies_4W'),
    ('CUR.vw_StoreProductAnomalies_4W'),
    ('CUR.vw_StoreProductBaselines'),
    ('CUR.vw_WeeklySales_Fact');

SELECT r.view_name AS missing_view
FROM @required r
WHERE OBJECT_ID(r.view_name, 'V') IS NULL
ORDER BY r.view_name;
