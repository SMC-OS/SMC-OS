class SlabCalculator:

    SLAB_LENGTH = 3.2
    SLAB_WIDTH = 1.6

    def calculate(self, request):
        # Total worktop length
        total_length = request.kitchen_length

        # Add island if present
        if request.island:
            total_length += 1.8   # temporary default

        slab_area = self.SLAB_LENGTH * self.SLAB_WIDTH

        # Temporary estimate
        slabs = 1

        if total_length > 3.2:
            slabs = 2

        return slabs