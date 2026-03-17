class CommandRegistry:

    def __init__(self):
        self.commands = {}

    def register(self, name, handler):
        """
        Register a command handler.
        """
        self.commands[name] = handler

    def get(self, name):
        """
        Get command handler.
        """
        return self.commands.get(name)

    def list_commands(self):
        return list(self.commands.keys())