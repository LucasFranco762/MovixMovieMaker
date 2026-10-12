# Instalação do MLT com bindings Python no Windows

Procedimento validado em 11/10/2026 com:

- Windows 64 bits;
- Python 3.13 64 bits na `.venv`;
- MLT 7.40.0;
- MSYS2 UCRT64;
- SWIG 4.5.1 e GCC UCRT 16.2.

## Situação importante

O módulo `mlt7` não possui wheel oficial para Windows no PyPI. O pacote MSYS2
instala o MLT completo e um binding para o Python do próprio MSYS2. Como a venv
do Movix usa outra versão do Python, `_mlt7.pyd` precisa ser recompilado contra
o executável da venv.

## Instalação usada neste computador

1. Instalar o MSYS2:

   ```powershell
   winget install --id MSYS2.MSYS2 --exact
   ```

2. No ambiente UCRT64, atualizar o sistema e instalar o MLT, compiladores e
   plugins. Além do pacote `mingw-w64-ucrt-x86_64-mlt`, foram instalados CMake,
   Ninja, SWIG, toolchain, FFmpeg, Frei0r, Qt6, RtAudio, Rubberband, SoX,
   libsamplerate e vid.stab.

3. Baixar o código-fonte da mesma versão do MLT instalada e configurar com:

   ```text
   -DSWIG_PYTHON=ON
   -DPython3_EXECUTABLE=<projeto>/.venv/Scripts/python.exe
   -DCMAKE_PREFIX_PATH=C:/msys64/ucrt64
   ```

4. Compilar o alvo `mltpython` e copiar `mlt.py` como `mlt7.py`, junto de
   `_mlt7.pyd`, para `.venv/Lib/site-packages`.

5. A venv deve adicionar `C:\msys64\ucrt64\bin` aos diretórios de DLL e definir:

   ```text
   MLT_REPOSITORY=C:\msys64\ucrt64\lib\mlt
   MLT_DATA=C:\msys64\ucrt64\share\mlt
   MLT_PROFILES_PATH=C:\msys64\ucrt64\share\mlt\profiles
   ```

   Neste computador isso é feito por
   `.venv/Lib/site-packages/movix_mlt_runtime.pth`.

## Validação

Execute:

```powershell
.\.venv\Scripts\python.exe -c "import mlt7; print(mlt7.__file__)"
.\.venv\Scripts\python.exe ferramentas\prova_conceito.py
```

Foram validados importação, inicialização, abertura de vídeo pelo `avformat`,
navegação, quadro RGBA, dois clipes, transição `luma`, mixagem de áudio e
exportação H.264/AAC. O aplicativo passa explicitamente o repositório de plugins
para `Factory.init`, pois builds relocáveis do MLT ignoram `MLT_REPOSITORY` no
Windows.

Referências oficiais:

- <https://www.mltframework.org/doxygen/group__python__bindings.html>
- <https://github.com/mltframework/mlt/blob/master/.github/workflows/build-msys2-mingw64.yml>
- <https://www.mltframework.org/docs/windowsbuild/>
