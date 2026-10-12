# Instalação do MLT com bindings Python no Windows

> **Este é o principal bloqueio técnico do projeto.** Nada aqui foi executado
> pelo autor: o ambiente de desenvolvimento foi Linux e não tinha MLT. As
> informações vêm de pesquisa e precisam ser confirmadas por você.

## O que a pesquisa mostrou

- Não há distribuição pronta (wheel do pip) dos bindings Python do MLT para
  Windows. O pacote MSYS2 `mingw-w64-*-mlt` (versão 7.40.0 na época da
  pesquisa) existe, mas a página não lista um pacote de bindings Python
  ([MSYS2](https://packages.msys2.org/base/mingw-w64-mlt)).
- A rota relatada por um usuário no fórum do Shotcut é compilar o MLT no
  **MSYS2** com `-D SWIG_PYTHON=ON` e Ninja. Ele encontrou problemas:
  `ImportError: DLL load failed while importing _mlt7` (DLLs `libgcc`/`libiconv`
  conflitantes vindas do PATH), e `Producer` com duração 0 porque o MLT procura
  seus arquivos de dados relativo ao executável (`python.exe`); a sugestão foi
  definir `MLT_DATA` / `MLT_PROFILES_PATH` e validar primeiro com `melt.exe`
  ([fórum Shotcut](https://forum.shotcut.org/t/have-anyone-make-python-bindings-on-windows-for-mltframwork/32943)).
  O próprio Shotcut disse não ter construído os bindings, então são dicas não verificadas.
- Guia oficial de build no Windows: <https://www.mltframework.org/docs/windowsbuild/>

## Riscos a testar (não verificados)

1. **ABI/compilador:** bindings compilados com MinGW (MSYS2) podem não carregar
   no Python "python.org" (MSVC). O caminho mais seguro tende a ser usar o
   **Python do próprio MSYS2** para tudo, o que exige PyQt6 do MSYS2
   (`mingw-w64-*-python-pyqt6`) em vez do wheel do pip. Confirmar a existência e versão.
2. **Módulos do MLT:** `avformat` (arquivos e exportação), `sdl2` (áudio),
   `qt`/`gdk` (texto/título) e `frei0r`/`movit` (filtros) variam conforme o build.
3. **Licenças:** FFmpeg com `--enable-gpl` e MLT (LGPL/GPL conforme módulos) afetam a
   distribuição futura. Ver `LICENCAS.md`.

## Caminho sugerido (a validar)

1. Instalar o MSYS2 e abrir o shell UCRT64.
2. `pacman -S mingw-w64-ucrt-x86_64-mlt` e conferir se `melt --version` funciona.
3. Se não houver bindings Python no pacote, compilar o MLT a partir do código-fonte com
   `-D SWIG_PYTHON=ON` (requer SWIG e Python do MSYS2).
4. No Python escolhido: `python -c "import mlt7; print(mlt7.__file__)"`.
5. Rodar `python ferramentas\prova_conceito.py --reproduzir-audio` e enviar
   `relatorio_poc.txt`.

## Se os bindings Python não funcionarem

O requisito proíbe trocar o motor silenciosamente, então **isso é uma decisão sua**.
Alternativas que continuam usando o MLT (nenhuma implementada):

- **A.** Controlar o MLT pelo executável `melt.exe` (subprocesso) gerando XML MLT
  a partir do modelo do projeto. Serve para exportar e gerar quadros. A reprodução
  interativa ficaria mais limitada.
- **B.** Escrever uma pequena extensão C++ própria, usando a API C do MLT (`libmlt`)
  via `ctypes`/`cffi`.
- **C.** Reavaliar o motor (fora do escopo aprovado; exige sua autorização).

A arquitetura isola o motor em `multimidia/motor_base.py`, então A ou B exigem
apenas uma nova implementação de `MotorMultimidia`.
