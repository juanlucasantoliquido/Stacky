@echo off
cd /d "%~dp0"

echo === TEST: Crear ticket de prueba ===
echo.

python ado.py create ^
  --title "[TEST] Ticket de prueba - ADO Manager CLI" ^
  --desc "Este ticket fue creado automaticamente por test_create.bat para verificar que el ADO Manager CLI funciona correctamente. Se puede eliminar." ^
  --type "Task" ^
  --priority 4 ^
  --tags "test;ado-manager"

echo.
echo === Listo. Verificar el resultado arriba ===
pause
