"""Plan 157 F1 — parser determinista de connection strings (sin red, sin LLM).

Ver Stacky Agents/docs/157_PLAN_DB_COMPARE_CONFIG_IN_PLACE_WEBCONFIG_IMPORT_Y_PANEL_MIGRACION.md
"""
from __future__ import annotations

import os
from dataclasses import asdict

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services.dbcompare_config_import import (  # noqa: E402
    ParsedConnection,
    parse_connection_string,
    parse_webconfig,
)


def test_sqlserver_user_pass():
    pc, pw = parse_connection_string("Server=srv,1433;Database=RS;User ID=rs;Password=Secr3t;")
    assert pc.engine == "sqlserver"
    assert pc.host == "srv"
    assert pc.port == 1433
    assert pc.database == "RS"
    assert pc.username == "rs"
    assert pc.has_password is True
    assert pw == "Secr3t"
    assert "Password=****" in pc.masked_raw
    assert "Secr3t" not in pc.masked_raw


def test_sqlserver_integrated_security():
    pc, pw = parse_connection_string(
        "Data Source=srv\\SQLEXPRESS;Initial Catalog=RS;Integrated Security=SSPI;"
    )
    assert pc.engine == "sqlserver"
    assert pc.integrated_security is True
    assert pc.host == "srv\\SQLEXPRESS"
    assert pc.port is None
    assert pc.has_password is False
    assert pw is None


def test_oracle_ezconnect():
    pc, pw = parse_connection_string(
        "Data Source=host1:1521/ORCL;User Id=u;Password=p;",
        provider_name="Oracle.ManagedDataAccess.Client",
    )
    assert pc.engine == "oracle"
    assert pc.host == "host1"
    assert pc.port == 1521
    assert pc.database == "ORCL"
    assert pc.username == "u"
    assert pc.has_password is True
    assert pw == "p"


def test_oracle_ezconnect_sin_provider_por_slash():
    # Sin provider: la señal literal `/` en el datasource alcanza para inferir Oracle.
    pc, _pw = parse_connection_string("Data Source=host1:1521/ORCL;User Id=u;Password=Secr3t;")
    assert pc.engine == "oracle"
    assert pc.host == "host1"
    assert pc.port == 1521
    assert pc.database == "ORCL"


def test_oracle_tns_descriptor():
    raw = "Data Source=(DESCRIPTION=(ADDRESS=(HOST=h)(PORT=1521)));User Id=u;Password=Secr3t;"
    pc, _pw = parse_connection_string(raw)
    assert pc.engine == "oracle"


def test_webconfig_multiples_conn():
    xml = """
    <configuration>
      <connectionStrings>
        <add name="Dev" providerName="System.Data.SqlClient"
             connectionString="Server=devsrv,1433;Database=RS;User ID=u;Password=Secr3t;" />
        <add name="Test" providerName="System.Data.SqlClient"
             connectionString="Server=testsrv,1433;Database=RS;User ID=u2;Password=Otr0Pass;" />
      </connectionStrings>
      <appSettings>
        <add key="foo" value="bar" />
      </appSettings>
    </configuration>
    """
    conns = parse_webconfig(xml)
    assert len(conns) == 2
    names = {pc.name for pc, _ in conns}
    assert names == {"Dev", "Test"}
    for pc, pw in conns:
        assert pc.engine == "sqlserver"
        assert pw in ("Secr3t", "Otr0Pass")
        assert "Secr3t" not in pc.masked_raw or pc.name == "Test"


def test_webconfig_xml_invalido_no_crashea():
    assert parse_webconfig("esto no es xml <<<") == []
    assert parse_webconfig("") == []


def test_password_nunca_en_parsedconnection():
    cases = [
        "Server=srv,1433;Database=RS;User ID=rs;Password=Secr3t;",
        "Data Source=host1:1521/ORCL;User Id=u;Password=MiClave123;",
        "Server=x;Database=y;User ID=z;Pwd=Alt3rn0;",
    ]
    for raw in cases:
        pc, pw = parse_connection_string(raw)
        assert pw is not None and pw != ""
        serialized = asdict(pc)
        for value in serialized.values():
            assert pw not in str(value), f"password fugó en {value!r}"


def test_pwd_alias_detectado():
    pc, pw = parse_connection_string("Server=x;Database=y;User ID=z;Pwd=Alt3rn0;")
    assert pw == "Alt3rn0"
    assert pc.has_password is True
    assert "Pwd=****" in pc.masked_raw


def test_dataclass_defaults_sin_password_field():
    # Blindaje de contrato: ParsedConnection NO tiene un campo 'password'.
    pc = ParsedConnection()
    assert "password" not in asdict(pc)
