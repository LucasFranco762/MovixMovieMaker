# Dependências e licenciamento

> Registro inicial. **Não é parecer jurídico.** Confirme as licenças reais das
> versões que você instalar antes de qualquer distribuição.

| Dependência | Uso | Licença (conhecimento geral, a confirmar) | Observação |
|---|---|---|---|
| PyQt6 | Interface | GPL v3 ou licença comercial (Riverbank) | Distribuir um app fechado exige licença comercial ou compatibilidade GPL. PySide6 (LGPL) seria alternativa, mas trocar a tecnologia aprovada exige decisão sua. |
| MLT Framework | Composição/reprodução | LGPL 2.1 no núcleo; alguns módulos GPL | Depende dos módulos habilitados no build. |
| FFmpeg | Análise e codecs | LGPL 2.1+ ou GPL v2+ conforme as opções do build | Builds com libx264/libx265 costumam ser GPL. |
| Codecs (H.264, HEVC, VP9, AV1) | Exportação | Variam; H.264/HEVC têm patentes | Verificar antes de distribuir. |

Uso local para avaliação, que é o escopo atual, não exige ação adicional.
Nenhuma decisão de licenciamento foi tomada nem a tecnologia de interface foi alterada.
