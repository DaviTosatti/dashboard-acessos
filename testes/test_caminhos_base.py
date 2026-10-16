"""Regressão de URI para unidades Windows, UNC e acesso somente para leitura."""
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing, contextmanager
from pathlib import Path, PureWindowsPath
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import parse_qs, unquote, urlsplit

from consulta import abrir_base, uri_somente_leitura


@contextmanager
def banco_temporario():
    with tempfile.TemporaryDirectory(prefix='dashboard com espaços ') as directory:
        banco = Path(directory) / 'base # 10% de produção.sqlite3'
        with closing(sqlite3.connect(banco)) as connection:
            connection.execute('CREATE TABLE exemplo (valor TEXT)')
            connection.execute('INSERT INTO exemplo VALUES (?)', ('confirmado',))
            connection.commit()
        yield banco


class CaminhosBaseTests(unittest.TestCase):
    def test_caminhos_windows_preservam_endereco_e_modo_de_leitura(self):
        caminhos = [
            (r'C:\Pasta com espaços\base # 10%.sqlite3', '/C:/Pasta com espaços/base # 10%.sqlite3'),
            (r'F:\pasta\base.sqlite3', '/F:/pasta/base.sqlite3'),
            (r'\\servidor\compartilhamento\Pasta com espaços\base # 10%.sqlite3',
             '//servidor/compartilhamento/Pasta com espaços/base # 10%.sqlite3'),
            (r'\\localhost\compartilhamento\base.sqlite3', '//localhost/compartilhamento/base.sqlite3'),
        ]
        for caminho, esperado in caminhos:
            with self.subTest(caminho=caminho):
                uri = urlsplit(uri_somente_leitura(PureWindowsPath(caminho)))
                self.assertEqual(uri.scheme, 'file')
                self.assertEqual(uri.netloc, '')
                self.assertEqual(unquote(uri.path), esperado)
                self.assertEqual(uri.fragment, '')
                self.assertEqual(parse_qs(uri.query), {'mode': ['ro']})

    def test_base_com_espacos_acentos_e_simbolos_continua_somente_leitura(self):
        with banco_temporario() as banco:
            with abrir_base(SimpleNamespace(banco=banco)) as connection:
                self.assertEqual(connection.execute('SELECT valor FROM exemplo').fetchone()[0], 'confirmado')
                with self.assertRaisesRegex(sqlite3.OperationalError, 'readonly'):
                    connection.execute('INSERT INTO exemplo VALUES (?)', ('alterado',))
            inexistente = banco.with_name('nao_criar.sqlite3')
            with self.assertRaises(sqlite3.OperationalError):
                sqlite3.connect(uri_somente_leitura(inexistente), uri=True)
            self.assertFalse(inexistente.exists())

    @unittest.skipUnless(os.name == 'posix', 'Simula uma URI UNC no sistema de arquivos local POSIX.')
    def test_regressao_invalid_uri_authority_no_sqlite_real(self):
        with banco_temporario() as banco:
            # O primeiro componente do caminho passa a ser a authority, reproduzindo o erro.
            uri_antiga = banco.as_uri().replace('file:///', 'file://', 1)
            with self.assertRaisesRegex(sqlite3.OperationalError, 'invalid uri authority'):
                sqlite3.connect(uri_antiga + '?mode=ro', uri=True)
            caminho_unc = Mock(wraps=banco)
            caminho_unc.as_uri.return_value = uri_antiga
            with abrir_base(SimpleNamespace(banco=caminho_unc)) as connection:
                self.assertEqual(connection.execute('SELECT valor FROM exemplo').fetchone()[0], 'confirmado')


if __name__ == '__main__':
    unittest.main()
