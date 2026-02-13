/* =========================================================
   Seed User: Aidan Harrington (CEO) with FULL access
   Database: Fusion_Dashboard
   Schema  : ADM

   Password is bcrypt hash of: login
   Idempotent script: safe to run multiple times.
   ========================================================= */

DECLARE @username       NVARCHAR(100) = N'Aidan';
DECLARE @email          NVARCHAR(255) = N'aidan.harrington@synoviadigital.com';

-- bcrypt hash for password: login
DECLARE @password_hash  NVARCHAR(255) = N'$2b$12$mKzRv3xTBoxWiJWSdCEES.wtClWhgFsy.Kye0VS6fft3GaiozOwI.';

DECLARE @first_name     NVARCHAR(100) = N'Aidan';
DECLARE @last_name      NVARCHAR(100) = N'Harrington';
DECLARE @role           NVARCHAR(50)  = N'CEO';
DECLARE @is_active      BIT           = 1;

DECLARE @user_id INT;

SELECT @user_id = user_id
FROM ADM.Users
WHERE email = @email OR username = @username;

IF @user_id IS NULL
BEGIN
    INSERT INTO ADM.Users (username, email, password_hash, first_name, last_name, role, is_active)
    VALUES (@username, @email, @password_hash, @first_name, @last_name, @role, @is_active);

    SET @user_id = SCOPE_IDENTITY();
END
ELSE
BEGIN
    UPDATE ADM.Users
    SET
        username      = @username,
        email         = @email,
        password_hash = @password_hash,
        first_name    = @first_name,
        last_name     = @last_name,
        role          = @role,
        is_active     = @is_active
    WHERE user_id = @user_id;
END

IF NOT EXISTS (SELECT 1 FROM ADM.UserProfile WHERE user_id = @user_id)
BEGIN
    INSERT INTO ADM.UserProfile (user_id, theme, default_module, landing_layout, kpi_preferences)
    VALUES (@user_id, N'light', N'Fusion Core', N'{}', N'{}');
END

UPDATE a
SET a.can_view = 1,
    a.can_edit = 1
FROM ADM.UserModuleAccess a
JOIN ADM.Modules m ON m.module_id = a.module_id
WHERE a.user_id = @user_id
  AND m.is_active = 1;

INSERT INTO ADM.UserModuleAccess (user_id, module_id, can_view, can_edit)
SELECT @user_id, m.module_id, 1, 1
FROM ADM.Modules m
WHERE m.is_active = 1
  AND NOT EXISTS (
      SELECT 1
      FROM ADM.UserModuleAccess a
      WHERE a.user_id = @user_id AND a.module_id = m.module_id
  );

SELECT @user_id AS seeded_user_id;
