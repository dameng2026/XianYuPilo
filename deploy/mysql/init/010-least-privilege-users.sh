#!/bin/sh
set -eu

# This file is processed by the official MySQL entrypoint only while creating a
# new data directory. Secrets arrive as service-scoped files; no real
# credentials are stored in the image, Compose environment, or repository.
: "${MYSQL_DATABASE:?MYSQL_DATABASE must be set}"
: "${MYSQL_ROOT_PASSWORD:?MYSQL_ROOT_PASSWORD must be set}"
: "${MYSQL_APP_USER:?MYSQL_APP_USER must be set}"
: "${MYSQL_MIGRATION_USER:?MYSQL_MIGRATION_USER must be set}"

file_env() {
  variable=$1
  file_variable="${variable}_FILE"
  direct_value=$(printenv "$variable" 2>/dev/null || true)
  file_path=$(printenv "$file_variable" 2>/dev/null || true)
  if [ -n "$direct_value" ] && [ -n "$file_path" ]; then
    echo "Database account provisioning found conflicting secret sources." >&2
    return 1
  fi
  if [ -n "$file_path" ]; then
    if [ ! -f "$file_path" ] || [ ! -r "$file_path" ]; then
      echo "Database account provisioning could not read a required secret file." >&2
      return 1
    fi
    direct_value=$(cat "$file_path")
  fi
  if [ -z "$direct_value" ]; then
    echo "Database account provisioning found an empty required secret." >&2
    return 1
  fi
  export "$variable=$direct_value"
  unset "$file_variable"
}

file_env MYSQL_APP_PASSWORD
file_env MYSQL_MIGRATION_PASSWORD

validate_identifier() {
  value=$1
  maximum=$2
  if ! printf '%s' "$value" | grep -Eq "^[A-Za-z0-9_]{1,${maximum}}$"; then
    echo "Database account provisioning rejected an invalid identifier." >&2
    return 1
  fi
}

validate_account_name() {
  validate_identifier "$1" 32
  normalized=$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')
  case "$normalized" in
    root|mysql|admin)
      echo "Database account provisioning rejected a reserved account name." >&2
      return 1
      ;;
  esac
}

validate_identifier "$MYSQL_DATABASE" 64
validate_account_name "$MYSQL_APP_USER"
validate_account_name "$MYSQL_MIGRATION_USER"
app_user_normalized=$(printf '%s' "$MYSQL_APP_USER" | tr '[:upper:]' '[:lower:]')
migration_user_normalized=$(printf '%s' "$MYSQL_MIGRATION_USER" | tr '[:upper:]' '[:lower:]')
if [ "$app_user_normalized" = "$migration_user_normalized" ]; then
  echo "Runtime and migration database accounts must be different." >&2
  exit 1
fi
if [ "$MYSQL_APP_PASSWORD" = "$MYSQL_MIGRATION_PASSWORD" ] || \
   [ "$MYSQL_APP_PASSWORD" = "$MYSQL_ROOT_PASSWORD" ] || \
   [ "$MYSQL_MIGRATION_PASSWORD" = "$MYSQL_ROOT_PASSWORD" ]; then
  echo "Root, migration, and runtime database credentials must be unique." >&2
  exit 1
fi

encode_value() {
  printf '%s' "$1" | base64 | tr -d '\r\n'
}

database_b64=$(encode_value "$MYSQL_DATABASE")
app_user_b64=$(encode_value "$MYSQL_APP_USER")
app_password_b64=$(encode_value "$MYSQL_APP_PASSWORD")
migration_user_b64=$(encode_value "$MYSQL_MIGRATION_USER")
migration_password_b64=$(encode_value "$MYSQL_MIGRATION_PASSWORD")

# MYSQL_PWD keeps the root credential out of the process argument list. Values
# interpolated below are base64, then quoted by MySQL before dynamic execution.
export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"
mysql --protocol=socket --user=root <<SQL
SET @database_name = CONVERT(FROM_BASE64('$database_b64') USING utf8mb4);
SET @app_user = CONVERT(FROM_BASE64('$app_user_b64') USING utf8mb4);
SET @app_password = CONVERT(FROM_BASE64('$app_password_b64') USING utf8mb4);
SET @migration_user = CONVERT(FROM_BASE64('$migration_user_b64') USING utf8mb4);
SET @migration_password = CONVERT(FROM_BASE64('$migration_password_b64') USING utf8mb4);
SET @database_identifier = CONCAT('`', REPLACE(@database_name, '`', '``'), '`');
SET @app_identity = CONCAT(QUOTE(@app_user), '@', QUOTE('%'));
SET @migration_identity = CONCAT(QUOTE(@migration_user), '@', QUOTE('%'));

SET @sql = CONCAT('CREATE USER IF NOT EXISTS ', @app_identity, ' IDENTIFIED BY ', QUOTE(@app_password));
PREPARE account_statement FROM @sql;
EXECUTE account_statement;
DEALLOCATE PREPARE account_statement;
SET @sql = CONCAT('ALTER USER ', @app_identity, ' IDENTIFIED BY ', QUOTE(@app_password));
PREPARE account_statement FROM @sql;
EXECUTE account_statement;
DEALLOCATE PREPARE account_statement;
SET @sql = CONCAT('REVOKE ALL PRIVILEGES, GRANT OPTION FROM ', @app_identity);
PREPARE account_statement FROM @sql;
EXECUTE account_statement;
DEALLOCATE PREPARE account_statement;
SET @sql = CONCAT('GRANT SELECT, INSERT, UPDATE, DELETE ON ', @database_identifier, '.* TO ', @app_identity);
PREPARE account_statement FROM @sql;
EXECUTE account_statement;
DEALLOCATE PREPARE account_statement;

SET @sql = CONCAT('CREATE USER IF NOT EXISTS ', @migration_identity, ' IDENTIFIED BY ', QUOTE(@migration_password));
PREPARE account_statement FROM @sql;
EXECUTE account_statement;
DEALLOCATE PREPARE account_statement;
SET @sql = CONCAT('ALTER USER ', @migration_identity, ' IDENTIFIED BY ', QUOTE(@migration_password));
PREPARE account_statement FROM @sql;
EXECUTE account_statement;
DEALLOCATE PREPARE account_statement;
SET @sql = CONCAT('REVOKE ALL PRIVILEGES, GRANT OPTION FROM ', @migration_identity);
PREPARE account_statement FROM @sql;
EXECUTE account_statement;
DEALLOCATE PREPARE account_statement;
SET @sql = CONCAT('GRANT ALL PRIVILEGES ON ', @database_identifier, '.* TO ', @migration_identity);
PREPARE account_statement FROM @sql;
EXECUTE account_statement;
DEALLOCATE PREPARE account_statement;
SQL
unset MYSQL_PWD
unset MYSQL_APP_PASSWORD MYSQL_MIGRATION_PASSWORD
unset MYSQL_APP_PASSWORD_FILE MYSQL_MIGRATION_PASSWORD_FILE
unset database_b64 app_user_b64 app_password_b64
unset migration_user_b64 migration_password_b64
