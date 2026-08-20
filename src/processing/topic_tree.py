class TopicNode:
    def __init__(self, value: str, path: list = None, parent=None, seen: set = None):
        """
        Initializes a TopicNode.

        Args:
            value (str): The current topic.
            path (list): The path from the root to this topic. Defaults to [value].
            parent (TopicNode): Parent node (used to inherit shared seen set).
            seen (set): Shared set for deduplication.
        """
        self.value = value
        self.path = path or [value]
        self.children = []
        self.parent = parent

        if seen is not None:
            self.seen = seen
        elif parent is not None:
            self.seen = parent.seen
        else:
            self.seen = set()

        self.seen.add(self._normalize(value))

    def _normalize(self, topic: str) -> str:
        """
        Normalize a topic string for deduplication.
        """
        return topic.strip().lower()

    def add_child(self, topic: str):
        """
        Adds a child node if it hasn't already been seen.

        Args:
            topic (str): The subtopic string.

        Returns:
            TopicNode or None: The child node or None if already seen.
        """
        normalized = self._normalize(topic)
        if normalized in self.seen:
            return None

        self.seen.add(normalized)
        new_path = self.path + [topic]
        child_node = TopicNode(topic, path=new_path, parent=self)
        self.children.append(child_node)
        return child_node

    def to_dict(self):
        """
        Convert this node and its subtree to a dictionary (for JSON export).

        Returns:
            dict: Dict representation of the node and children.
        """
        return {
            "value": self.value,
            "path": self.path,
            "children": [child.to_dict() for child in self.children]
        }

    def flatten(self):
        """
        Flatten tree into list of (topic, path) tuples.

        Returns:
            list[tuple[str, list[str]]]
        """
        results = [(self.value, self.path)]
        for child in self.children:
            results.extend(child.flatten())
        return results
    
    def flatten_unique_topics(self):
        """
        Returns a list of unique topics tracked by the tree.

        Since `self.seen` is shared among all nodes, returning it as a list
        provides all unique topics seen so far.
        """
        return list(self.seen)
    
    def get_leaves(self):
        """
        Returns a list of leaf nodes' values (nodes with no children).
        """
        if not self.children:
            return [self.value]
        
        leaves = []
        for child in self.children:
            leaves.extend(child.get_leaves())
        return leaves

    def to_jsonl_rows(self):
        """
        Returns a list of dicts, each representing a line for a JSONL file with:
        - 'topic': lowest internal node with children
        - 'search_queries': all leaf values under that topic
        - 'parents': path leading to the topic (excluding the topic itself)
        """
        rows = []

        # Helper to check if this node is a "lowest" topic node
        def is_topic_node(node):
            return node.children and all(not child.children for child in node.children)

        if is_topic_node(self):
            row = {
                "topic": self.value,
                "search_queries": [child.value for child in self.children],
                "parents": self.path[:-1]
            }
            rows.append(row)
        else:
            for child in self.children:
                rows.extend(child.to_jsonl_rows())

        return rows

    def __repr__(self):
        return f"TopicNode(value={self.value}, path={self.path}, children={len(self.children)})"
    
    @staticmethod
    def from_dict(data):
        node = TopicNode(data["value"], path=data["path"])
        for child in data.get("children", []):
            node.children.append(TopicNode.from_dict(child))
        return node
    
    @staticmethod
    def rebuild_from_jsonl_rows(rows: list[dict]) -> 'TopicNode':
        if not rows:
            raise ValueError("No rows to rebuild from.")

        # Use the first row to initialize the root based on the first parent
        first_parents = rows[0].get("parents", [])
        if not first_parents:
            raise ValueError("First row has no 'parents' field.")

        # Build initial root path
        root = TopicNode(first_parents[0])
        current = root
        for val in first_parents[1:]:
            current = current.add_child(val)

        for row in rows:
            parents = row.get("parents", [])
            topic = row["topic"]
            queries = row.get("search_queries", [])

            # Walk from root through parents
            current = root
            for p in parents[1:]:  # Skip root since it's already handled
                match = next((c for c in current.children if c.value == p), None)
                if match:
                    current = match
                else:
                    current = current.add_child(p)

            # Add topic node
            topic_node = next((c for c in current.children if c.value == topic), None)
            if not topic_node:
                topic_node = current.add_child(topic)

            # Add search queries under topic node
            for query in queries:
                topic_node.add_child(query)

        return root
    
    def get_non_leaf_count(self):
        if not self.children:
            return 0
        return 1 + sum(child.get_non_leaf_count() for child in self.children)

