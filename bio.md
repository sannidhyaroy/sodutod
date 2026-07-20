a soduto daemon · pid 1 of soduto labs

● sodutod.service - a soduto daemon
     Loaded: loaded (ghcr.io/sannidhyaroy/sodutod:{build}; enabled)
     Drop-In: /opt/stacks/sodutod
                    ┗━.env, compose.yaml
       Active: active (running) since {since}
  Main PID: 1 (sodutod)
         Tasks: {tasks}
     CGroup: /system.slice/sodutod.service
                    ┗━1 uv run main.py