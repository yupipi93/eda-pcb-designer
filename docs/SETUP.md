# Setup — KiCad 9 + kicad-mcp + kicad-sch-api en Ubuntu 24

> ⚠️ **Cambio de versión 2026-05-19**: el proyecto pasó de **KiCad 10** a **KiCad 9.0.7-1** porque el nuevo formato `.kicad_symdir/` de KiCad 10 rompe `kicad-sch-api` (necesario para construir esquemáticos programáticamente). Esta guía refleja la versión actual.

Guía paso a paso para dejar el entorno preparado. Se hace **una sola vez por máquina**. Todos los comandos asumen Ubuntu 24.04 LTS y un usuario sin permisos de root para `/usr` (usamos `~/.local/` y AppImage).

> **Alternativa con root**: si puedes usar `sudo`, el PPA oficial instala KiCad 9
> de sistema y te ahorras la sección 1 completa:
> `sudo add-apt-repository -y ppa:kicad/kicad-9.0-releases && sudo apt install -y kicad kicad-symbols kicad-footprints`.
> El [`Dockerfile`](../Dockerfile) del repo usa exactamente esa vía si prefieres
> no instalar nada en el host.

---

## 1. Instalar KiCad 9 desde AppImage

```bash
# 1.1 Descargar el AppImage stable 9.x
cd ~/Downloads
curl -L -o kicad-9.0.7-1-x86_64.AppImage \
  "https://downloads.kicad.org/kicad/linux/explore/stable/download/kicad-9.0.7-1-x86_64.AppImage"

# 1.2 Crear carpeta para AppImages del usuario
mkdir -p ~/.local/share/AppImages
cp kicad-9.0.7-1-x86_64.AppImage ~/.local/share/AppImages/
chmod +x ~/.local/share/AppImages/kicad-9.0.7-1-x86_64.AppImage

# 1.3 Extraer el contenido (acceso a símbolos, footprints y demos)
cd ~/.local/share/AppImages
./kicad-9.0.7-1-x86_64.AppImage --appimage-extract
mv squashfs-root kicad-9.0.7

# 1.4 Wrappers en ~/.local/bin/ (invocan vía launcher AppImage para evitar GLIBC mismatch)
mkdir -p ~/.local/bin
cat > ~/.local/bin/kicad <<'EOF'
#!/bin/sh
exec ~/.local/share/AppImages/kicad-9.0.7-1-x86_64.AppImage "$@"
EOF
cat > ~/.local/bin/kicad-cli <<'EOF'
#!/bin/sh
exec ~/.local/share/AppImages/kicad-9.0.7-1-x86_64.AppImage kicad-cli "$@"
EOF
chmod +x ~/.local/bin/kicad ~/.local/bin/kicad-cli

# 1.5 Verificar
kicad-cli --version    # debería responder "9.0.7"
```

> Las librerías de símbolos quedan en `~/.local/share/AppImages/kicad-9.0.7/usr/share/kicad/symbols/` (formato `.kicad_sym` clásico, compatible con `kicad-sch-api`).

> Si `~/.local/bin` no está en tu PATH, añade `export PATH="$HOME/.local/bin:$PATH"` a tu `~/.zshrc` y abre una nueva terminal.

### 1.b Integración con el escritorio (opcional)

Para que aparezca KiCad en el menú de aplicaciones:

```bash
mkdir -p ~/.local/share/applications ~/.local/share/icons
cp ~/.local/share/AppImages/kicad-9.0.7/kicad.desktop ~/.local/share/applications/
cp ~/.local/share/AppImages/kicad-9.0.7/usr/share/icons/hicolor/256x256/apps/kicad.png ~/.local/share/icons/
# Editar el .desktop para apuntar al binario real
sed -i 's|Exec=kicad|Exec=/home/'"$USER"'/.local/bin/kicad|' ~/.local/share/applications/kicad.desktop
sed -i 's|Icon=kicad|Icon=/home/'"$USER"'/.local/share/icons/kicad.png|' ~/.local/share/applications/kicad.desktop
update-desktop-database ~/.local/share/applications/ 2>/dev/null || true
```

---

## 1.5. Instalar el paquete `pcb-designer` (venv local del proyecto)

El paquete Python instalable vive en `src/pcb_designer/`. El venv
canónico es **local al repo** y proporciona el console_script
`pcb-designer` + todas las dependencias (incluyendo `kicad-sch-api` y
`Pillow`).

```bash
# Desde la raíz del repo eda-pcb-designer/
cd <repo-root>

# 1.5.1 Crear el venv local
python3 -m venv .venv

# 1.5.2 Activarlo
source .venv/bin/activate

# 1.5.3 Instalar el paquete en modo editable con todos los extras
python3 -m pip install --upgrade pip
python3 -m pip install -e '.[schematic,render,dev]'
#   schematic → kicad-sch-api (build programático del .kicad_sch)
#   render    → Pillow (overlays + recortes de renders)
#   dev       → pytest + pytest-cov (suite de tests)

# 1.5.4 Variable de entorno para que kicad-sch-api encuentre las librerías
export KICAD_SYMBOL_DIR=~/.local/share/AppImages/kicad-9.0.7/usr/share/kicad/symbols

# 1.5.5 Verificar
pcb-designer --help
pcb-designer validate --config examples/mt1.yaml
pytest tests -q
```

> **IMPORTANTE — usa `python3 -m pip`, no `pip` pelado**: en sistemas
> con Cursor/AppImages instalados, el binario `pip` directo puede
> apuntar a un launcher AppImage (Cursor) y abrir una ventana del
> editor en vez de instalar. La forma `python3 -m pip` siempre invoca
> el pip del venv activo.

### Subcomandos disponibles del CLI

```bash
pcb-designer validate   --config <yaml>        # typecheck del YAML
pcb-designer gallery    --renders-dir <dir>    # regenerar INDEX.md
pcb-designer schematic  --config <yaml>        # build_schematic
pcb-designer place      --config <yaml>        # place_components
pcb-designer route      --config <yaml>        # autorouter
pcb-designer render     --config <yaml>        # renders DIM + overlay
pcb-designer pipeline   --config <yaml> --stages place,route,render
pcb-designer fab        --config <yaml> --version vX.Y.Z   # gerbers+drill+BOM+pos zip
# init, migrate — stubs (cmd_pending)
```

### Flujo legacy directo (sin CLI)

Los scripts MT1-específicos siguen siendo invocables con el venv activo:

```bash
python3 projects/mt1/tools/build_schematic.py    # solo si cambian pinouts
python3 projects/mt1/tools/place_components.py   # placement + render
python3 projects/mt1/tools/run_autorouter.py     # autorouter end-to-end
```

## 2. Instalar `uv` (gestor de Python venv)

`kicad-mcp` usa `uv` (de Astral) para gestionar su entorno virtual.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
# Recargar la shell o ejecutar:
source $HOME/.local/bin/env

uv --version    # debería mostrar 0.8.x o superior
```

---

## 3. Clonar e instalar `kicad-mcp`

El MCP server es una **herramienta externa al proyecto** (no va dentro de este repo). Lo instalamos en `~/code/tools/kicad-mcp`.

```bash
mkdir -p ~/code/tools
cd ~/code/tools
git clone https://github.com/lamaalrajih/kicad-mcp.git
cd kicad-mcp

# Crea el venv con uv e instala dependencias
make install

# Activar el venv (sólo para test manual; el MCP server lo activará solo)
source .venv/bin/activate

# Configurar .env apuntando al proyecto KiCad
cp .env.example .env
```

Edita `~/code/tools/kicad-mcp/.env` y deja:

```ini
# Rutas donde el MCP buscará proyectos .kicad_pro
KICAD_SEARCH_PATHS=<repo-root>/pcb

# Opcional: forzar la ruta de los binarios de KiCad (AppImage extraído)
KICAD_APP_PATH=/home/USERNAME/.local/share/AppImages/kicad-9.0.7
```

> Sustituye `USERNAME` por tu usuario real (`echo $USER`).

### Test manual del servidor

```bash
cd ~/code/tools/kicad-mcp
source .venv/bin/activate
python main.py
# Debería arrancar y quedar a la espera de conexiones MCP por stdin/stdout.
# Pulsa Ctrl+C para cerrar.
```

---

## 4. Configurar Claude Code para usar el MCP

Hay dos opciones:

### Opción A — Workspace-level (recomendada para este proyecto)

Crea `.mcp.json` en la raíz de tu workspace o del proyecto:

```bash
# Ruta sugerida (workspace-level)
nano <workspace>/.mcp.json
```

Contenido:

```json
{
  "mcpServers": {
    "kicad": {
      "command": "/home/USERNAME/code/tools/kicad-mcp/.venv/bin/python",
      "args": ["/home/USERNAME/code/tools/kicad-mcp/main.py"]
    }
  }
}
```

Sustituye `USERNAME`. Cuando lances Claude Code dentro del workspace, te pedirá aprobar el MCP la primera vez.

### Opción B — User-level (siempre activo)

Añadir al fichero `~/.claude.json` el mismo bloque `mcpServers`. Útil si quieres el MCP disponible en cualquier sesión, no sólo dentro del workspace.

> **Comando alternativo**: en Claude Code puedes correr `claude mcp add kicad /home/USERNAME/code/tools/kicad-mcp/.venv/bin/python /home/USERNAME/code/tools/kicad-mcp/main.py` y se configura solo.

---

## 4.b Instalar el autorouter (v0.0.16+)

Para el rutado automático (`projects/mt1/tools/run_autorouter.py`) necesitas
Java 21+ porque freerouting v2.x está compilado para esa versión. Se
instala **en paralelo** al Java 11 que pueda haber en el sistema — no
pisa el default — porque el script apunta al binario explícito.

```bash
# 4.b.1 Java 21 (headless es suficiente)
sudo apt install -y openjdk-21-jre-headless

# 4.b.2 Verifica
/usr/lib/jvm/java-21-openjdk-amd64/bin/java -version
#  → openjdk version "21.x.x"
```

El JAR de **freerouting v2.1.0** NO está commiteado (64 MB): se
descarga una vez por clone con el script pineado y verificado por
SHA-256:

```bash
./vendor/fetch-freerouting.sh   # → vendor/freerouting.jar
```

Después, `projects/mt1/tools/run_autorouter.py` lo encuentra solo (vía
`pcb_designer.autorouter.find_java21`).

**Verificación end-to-end del autorouter** (debe correr ~6 s):

```bash
cd <repo-root>
source .venv/bin/activate
python3 projects/mt1/tools/run_autorouter.py
#  → Exporting DSN (mt1-pcb.dsn)
#  → Running freerouting (autorouter) ✓ in ~3 s
#  → Importing SES + filling zones + saving ✓
```

Si falla por `freerouting.jar not found`, ejecuta
`./vendor/fetch-freerouting.sh` (o descárgalo manualmente desde
`https://github.com/freerouting/freerouting/releases/download/v2.1.0/freerouting-2.1.0.jar`
hacia `vendor/freerouting.jar`).

## 5. Verificación final

1. Cierra cualquier sesión de Claude Code abierta.
2. Abre Claude Code en el repo (`cd <repo-root> && claude`).
3. Aprueba el MCP cuando lo pida.
4. Pídeme algo como: *"lista los proyectos KiCad disponibles"* — debería responder usando el MCP.

Si todo funciona, las herramientas que tendré disponibles incluyen:

- `list_projects` / `open_project` — listar y abrir proyectos KiCad
- `analyze_schematic` / `analyze_pcb` — leer netlist, componentes, layers
- `extract_bom` — generar BOM
- `run_drc` / `run_erc` — validación headless
- `visualize_pcb` — generar imagen del layout
- `identify_patterns` — detectar bloques típicos (regulador LDO, conector USB, etc.)

---

## Troubleshooting

| Síntoma | Causa probable | Fix |
|---|---|---|
| `kicad-cli: command not found` | `~/.local/bin` no en PATH | Añadir `export PATH="$HOME/.local/bin:$PATH"` a `~/.zshrc` |
| `uv: command not found` después de instalar | Shell no recargada | `source ~/.local/bin/env` o nueva terminal |
| Claude Code no detecta `kicad` MCP | `.mcp.json` mal formado / paths no absolutos | Revisa con `claude mcp list` |
| El MCP arranca pero no encuentra proyectos | `KICAD_SEARCH_PATHS` mal puesto | Usar **rutas absolutas** en `.env`, no `~/` (algunas versiones no lo expanden) |
| `Java 21+ not found` al correr autorouter | Java 21 no instalado | `sudo apt install -y openjdk-21-jre-headless` |
| `LinkageError: class file version 65 ... 55` | Estás usando Java 11 contra freerouting v2 | El script `run_autorouter.py` busca Java 21 en paths conocidos; añade el tuyo a `JAVA_BIN_CANDIDATES` si está en otro sitio |
| `ImportSpecctraSES returned False` | freerouting falló silenciosamente | Mira `projects/mt1/validation/freerouting.log`. Causa habitual: el board ya está pre-rutado y freerouting v2 no escribe el SES (mi script ya lo strippa antes — si falla, borra tracks a mano en GUI) |
| Quieres reinstalar | — | `cd ~/code/tools/kicad-mcp && rm -rf .venv && make install` |

---

## Referencias

- [lamaalrajih/kicad-mcp (GitHub)](https://github.com/lamaalrajih/kicad-mcp)
- [KiCad 10 release notes](https://www.kicad.org/)
- [uv (Astral)](https://github.com/astral-sh/uv)
- [AppImage extraction](https://docs.appimage.org/user-guide/run-appimages.html#type-1-image-format)
