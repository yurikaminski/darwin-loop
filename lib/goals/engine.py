class GoalValidator:
    def __init__(self, config):
        self.config = config

    def evaluate(self, metrics):
        if "max_messages" in self.config and "message_count" in metrics:
            if metrics["message_count"] > self.config["max_messages"]:
                return False
        
        if "max_tokens" in self.config and "total_tokens" in metrics:
            if metrics["total_tokens"] > self.config["max_tokens"]:
                return False
                
        return True
