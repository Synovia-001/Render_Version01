/*
  Seed EPOS module + access (Portal DB: Fusion_Dashboard / schema ADM)

  - Ensures the EPOS module exists in ADM.Modules
  - Grants can_view + can_edit for a selected user (lookup by email OR username)

  IMPORTANT:
  - Run this in the PORTAL database (DB_DATABASE, e.g. Fusion_Dashboard)
  - This does NOT create the EPOS views; those live in the EPOS database.
*/

-- USE [Fusion_Dashboard];
-- GO

DECLARE @module_url NVARCHAR(200) = '/module/EPOS';
DECLARE @module_name NVARCHAR(100) = 'Fusion EPOS';
DECLARE @icon NVARCHAR(100) = 'bi bi-speedometer2';

DECLARE @login NVARCHAR(200) = 'aidan.harrington@synoviadigital.com'; -- change to username/email

-- Upsert module
IF NOT EXISTS (SELECT 1 FROM ADM.Modules WHERE module_url IN (@module_url, @module_url + '/'))
BEGIN
    INSERT INTO ADM.Modules(module_name, module_url, icon, is_active, created_at)
    VALUES (@module_name, @module_url, @icon, 1, SYSDATETIME());
END

DECLARE @module_id INT = (SELECT TOP 1 module_id FROM ADM.Modules WHERE module_url IN (@module_url, @module_url + '/') ORDER BY module_id DESC);

-- Find user
DECLARE @user_id INT =
    (SELECT TOP 1 user_id FROM ADM.Users WHERE email = @login OR username = @login);

IF @user_id IS NULL
BEGIN
    RAISERROR('User not found in ADM.Users for login: %s', 16, 1, @login);
    RETURN;
END

-- Upsert access
IF EXISTS (SELECT 1 FROM ADM.UserModuleAccess WHERE user_id = @user_id AND module_id = @module_id)
BEGIN
    UPDATE ADM.UserModuleAccess
    SET can_view = 1, can_edit = 1
    WHERE user_id = @user_id AND module_id = @module_id;
END
ELSE
BEGIN
    INSERT INTO ADM.UserModuleAccess(user_id, module_id, can_view, can_edit, created_at)
    VALUES (@user_id, @module_id, 1, 1, SYSDATETIME());
END

SELECT 'OK' AS status, @user_id AS user_id, @module_id AS module_id, @module_url AS module_url;
