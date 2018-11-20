**Plugin script for exporting [Dia database diagram] to PostgreSQL.**

To add the plugin as an export type, copy `postgresql.py` to `$HOME/.dia/python/`.

Running the plugin from command line for automation or debugging:

    dia -e output.sql design_diagram.dia 

Inspired by:
- [postdia]
- [diasql.py]
- And other resources from the [Dia Python Plugin] page. 


[Dia database diagram]: http://dia-installer.de/shapes/Database/index.html
[Dia Python Plugin]: https://wiki.gnome.org/Apps/Dia/Python
[diasql.py]: https://github.com/fitorec/diasql/
[postdia]: https://github.com/chebizarro/postdia
